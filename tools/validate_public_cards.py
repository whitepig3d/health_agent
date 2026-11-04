"""Offline integrity checks for the unreviewed public evidence collection."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1] / 'knowledge' / 'public'
COUNTS = {'COMMON': 3, 'PLAN': 5, 'ASK': 4, 'RESULT': 3, 'WEIGHT': 2,
          'BP': 3, 'LIPID': 3, 'GLUCOSE': 4, 'FIBER': 1, 'ACT': 4,
          'SAFE': 2, 'OLDER': 2, 'ALC': 3, 'SMOKE': 3, 'SLEEP': 4,
          'NONOBESE': 1}
PDF_LENGTHS = {'PROGRAM_BASIC': 7, 'PROGRAM_IMPL': 72, 'QUESTIONNAIRE': 48,
               'FEEDBACK': 45, 'SMOKING': 17, 'NON_OBESE': 11,
               'SLEEP': 51, 'ALCOHOL': 17}


def check(condition, message):
    if not condition:
        raise ValueError(message)


def validate():
    cards = json.loads((ROOT / 'evidence_cards.json').read_text())
    sources = json.loads((ROOT / 'sources.json').read_text())
    index = (ROOT / '根拠カード一覧.md').read_text()
    source_map = {s['document_id']: s for s in sources}
    check(len(source_map) == len(sources) == 16, '出典IDの重複または資料数の不一致')
    ids = [c['evidence_id'] for c in cards]
    expected = {f'PUB_{prefix}_{i:02d}' for prefix, n in COUNTS.items()
                for i in range(1, n + 1)}
    check(len(ids) == len(set(ids)) == 47 and set(ids) == expected,
          'ID重複・テーマ欠落・収録数の不一致')
    check({c['document_id'] for c in cards} == set(source_map), '未参照の出典または不明な出典')
    for source in sources:
        check(urlparse(source['url']).hostname in {'www.mhlw.go.jp', 'kennet.mhlw.go.jp'},
              '想定外の出典ホスト')
        check(source['source_file_sha256'] is None, '未取得原本のハッシュを設定しない')
    for card in cards:
        name = card['evidence_id']
        source = source_map[card['document_id']]
        for key in ('title', 'text', 'section', 'edition', 'retrieved_at'):
            check(isinstance(card[key], str) and card[key].strip(), f'{name}: {key}不足')
        for key in ('url', 'edition', 'publisher', 'retrieved_at'):
            check(card[key] == source[key], f'{name}: 出典台帳との{key}不一致')
        for key in ('conditions', 'applicability', 'exclusions'):
            check(isinstance(card[key], list) and card[key]
                  and all(isinstance(x, str) and x.strip() for x in card[key]),
                  f'{name}: {key}不足')
        check(card['conditions'] == card['applicability'], f'{name}: 適用条件の不一致')
        check(card['reviewed'] is False and card['review_status'] == 'pending_expert_review'
              and card['reviewer_id'] is None and card['reviewed_at'] is None,
              f'{name}: レビュー前パックの状態と矛盾')
        check(card['excerpt'] is None and card['text_kind'] == 'author_summary',
              f'{name}: 引用と要約の区分不正')
        check(card['source_file_sha256'] is None, f'{name}: 原本未取得状態と矛盾')
        if source['format'] == 'pdf':
            page = card['page']
            check(page and page['printed'] and page['pdf_1based']
                  and all(type(p) is int and 1 <= p <= PDF_LENGTHS[source['document_id']]
                          for p in page['pdf_1based']), f'{name}: ページ番号不正')
        else:
            check(card['page'] is None, f'{name}: HTMLの架空ページ番号')
        content = {k: v for k, v in card.items() if k != 'card_sha256'}
        canonical = json.dumps(content, ensure_ascii=False, sort_keys=True,
                               separators=(',', ':'), allow_nan=False).encode()
        check(hashlib.sha256(canonical).hexdigest() == card['card_sha256'], f'{name}: ハッシュ不一致')
        check(f'## {name}：{card["title"]}' in index and card['text'] in index
              and card['url'] in index, f'{name}: Markdownとの不一致')
    print(f'OK: {len(cards)} cards / {len(sources)} sources; all pending expert review')


if __name__ == '__main__':
    validate()
