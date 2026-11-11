"""Explicit editorial classification for the public corpus (not clinical approval)."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'knowledge' / 'public'
INDIVIDUAL = {f'individual:{x}' for x in ('relevant', 'not_relevant', 'undetermined')}


def basis_hash(card):
    """Invalidate classification when its text, conditions or provenance changes."""
    fields = ('evidence_id', 'title', 'text', 'conditions', 'card_type',
              'source_excerpt_sha256', 'source_id', 'edition', 'source_location')
    basis = {k: card[k] for k in fields}
    if card['card_type'] == 'integrated_summary':
        basis.update({k: card[k] for k in ('citations', 'sections', 'related_detail_ids', 'theme_id')})
    if card.get('source_policy'):
        basis['source_policy'] = card['source_policy']
    raw = json.dumps(basis, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def load_taxonomy(root=ROOT):
    taxonomy = json.loads((root / 'tag_taxonomy.json').read_text())
    definitions = taxonomy['tags']
    ids = [d['id'] for d in definitions]
    if any(t.startswith(('use:', 'operation:')) for t in ids):
        raise ValueError('Retired namespace in taxonomy')
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate taxonomy tag')
    for d in definitions:
        if not all(d.get(k) for k in ('label', 'include', 'exclude', 'example_ids')):
            raise ValueError(f'Incomplete definition: {d["id"]}')
    for old, targets in taxonomy['legacy_aliases'].items():
        if old in ids or not targets or not set(targets) <= set(ids):
            raise ValueError(f'Invalid legacy alias: {old}')
    return taxonomy


def load_classifications(root=ROOT):
    ledger = json.loads((root / 'card_classifications.json').read_text())
    entries = ledger['cards']
    mapping = {r['evidence_id']: r for r in entries}
    if len(mapping) != len(entries):
        raise ValueError('Duplicate classification ID')
    return ledger, mapping


def validate_classifications(cards, taxonomy, ledger):
    definitions = {d['id']: d for d in taxonomy['tags']}
    entries = ledger['cards']
    mapping = {r['evidence_id']: r for r in entries}
    ids = {c['evidence_id'] for c in cards}
    if len(ids) != len(cards) or len(mapping) != len(entries) or set(mapping) != ids:
        raise ValueError('Classification IDs must match corpus exactly (no duplicates, missing or extra IDs)')
    if ledger['taxonomy_version'] != taxonomy['version']:
        raise ValueError('Classification taxonomy version mismatch')
    for c in cards:
        cid = c['evidence_id']
        r = mapping[cid]
        tags = set(r['tags'])
        if len(tags) != len(r['tags']) or not tags <= definitions.keys():
            raise ValueError(f'Unknown or duplicate tags: {cid}')
        if len(tags & INDIVIDUAL) != 1:
            raise ValueError(f'Exactly one individual classification required: {cid}')
        if not isinstance(r['reason'], str) or not r['reason'].strip():
            raise ValueError(f'Classification reason required: {cid}')
        if r['status'] != 'editorial_draft' or r['basis_sha256'] != basis_hash(c):
            raise ValueError(f'Stale or unapproved classification state: {cid}')
        scope = r['individual_scope']
        if not isinstance(scope, str):
            raise ValueError(f'Invalid individual scope: {cid}')
        if 'individual:relevant' in tags:
            if not scope.strip() or c['card_type'] == 'historical_reference':
                raise ValueError(f'Invalid individual relevance: {cid}')
        elif 'individual:not_relevant' in tags and scope:
            raise ValueError(f'Non-relevant card has personal use: {cid}')
        elif 'individual:undetermined' in tags and scope:
            raise ValueError(f'Undetermined card must not claim an established individual scope: {cid}')
    for c in cards:
        if c['card_type'] == 'integrated_summary':
            expected = {d['id'] for d in definitions.values() if c['evidence_id'] in d.get('integrated_card_ids', [])}
            actual = {t for t in mapping[c['evidence_id']]['tags'] if t.startswith('task:')}
            if len(expected) != 1 or actual != expected:
                raise ValueError(f'Integrated task mismatch: {c["evidence_id"]}')
    for d in definitions.values():
        if not set(d['example_ids']) <= ids:
            raise ValueError(f'Unknown example ID: {d["id"]}')
        if not all(d['id'] in mapping[eid]['tags'] for eid in d['example_ids']):
            raise ValueError(f'Example does not carry tag: {d["id"]}')
    return mapping


def apply_classifications(cards, root=ROOT):
    taxonomy = load_taxonomy(root)
    ledger, _ = load_classifications(root)
    mapping = validate_classifications(cards, taxonomy, ledger)
    for c in cards:
        entry = mapping[c['evidence_id']]
        c['tags'] = list(entry['tags'])
        c['classification'] = {k: entry[k] for k in ('reason', 'individual_scope', 'status')}
        c['classification']['taxonomy_version'] = taxonomy['version']


def resolve_tag(tag, taxonomy):
    if tag.startswith(('use:', 'operation:')) or tag in taxonomy.get('retired_tags', []):
        raise ValueError(f'Retired tag: {tag}; use individual/task/topic filters')
    if tag in {d['id'] for d in taxonomy['tags']}:
        return {tag}
    if tag in taxonomy['legacy_aliases']:
        return set(taxonomy['legacy_aliases'][tag])
    raise ValueError(f'Unknown tag: {tag}')


def render_tag_guide(cards, root=ROOT):
    taxonomy = load_taxonomy(root)
    groups = [[c for c in cards if c['card_type'] == kind] for kind in ('summary', 'integrated_summary')]
    groups.append([c for c in cards if c['card_type'] not in ('summary', 'integrated_summary')])
    counts = [Counter(t for c in group for t in c['tags']) for group in groups]
    def link(cid):
        card = next(c for c in cards if c['evidence_id'] == cid)
        path = '統合カード一覧.md' if card['card_type'] == 'integrated_summary' else '根拠カード一覧.md' if card['card_type'] == 'summary' else f'references/{card["source_id"]}.md'
        return f'[{cid}]({path}#{cid.lower()})'
    lines = ['# タグ整理・検索ガイド', '', f'分類版：{taxonomy["version"]}。全{len(cards)}枚。individual・task・topicの3軸。', '',
             '`use:`・`operation:`は廃止し、カードにも検索別名にも保持しません。廃止タグを検索すると明示的にエラーになります。', '',
             '## taskの定義', '',
             'HB43限定版16枚を軸に、複数出典版の禁煙支援・委託を加えた18業務。腹囲・体重アウトカムはポイント総合判定へ含めます。'
             '統合カードは主業務を1つ持ち、詳細要点・原文参照は説明する具体的業務を複数持てます。'
             '単に関連カードとして参照されたという理由で、その統合カードの全タグを継承しません。'
             '実績集計・事業評価・旧制度履歴等、対応する業務がないものはtaskなしを認めます。', '',
             '個人業務との関連は引き続きindividualで判定し、本人への適用条件や専門職の承認と区別します。taskの有無だけで個人利用の可否を決めません。', '',
             '詳細要点146枚と統合38枚はIDごとに主題を選別しました。原文参照は既存の編集分類と詳細要点の出典範囲を基に移行し、全原文の専門職再レビューを行ったものではありません。'
             '分類台帳にカードごとのtask_reasonを保持します。生成時には旧タグや本文の語句から分類を推定しません。', '']
    for prefix,label in [('task:','業務と対応する統合カード'),('individual:','個人業務との関連'),('topic:','健康・生活の話題')]:
        lines += [f'## {label}', '', '|タグ・名称|付与条件|除外条件|詳細|統合|原文|対応・代表カード|', '|---|---|---|---:|---:|---:|---|']
        for d in taxonomy['tags']:
            if not d['id'].startswith(prefix):continue
            examples = d.get('integrated_card_ids', d['example_ids'])
            lines.append(f"|`{d['id']}` {d['label']}|{d['include']}|{d['exclude']}|{counts[0][d['id']]}|{counts[1][d['id']]}|{counts[2][d['id']]}|{', '.join(link(e) for e in examples)}|")
        lines.append('')
    lines += ['## 旧名の検索別名', '', '分割先はOR、複数の--tag指定はANDです。新しい付与条件に従うため旧版と検索件数が一致する保証はありません。', '', '|旧名|新タグ（OR）|', '|---|---|']
    for old,targets in taxonomy['legacy_aliases'].items():lines.append(f"|`{old}`|{', '.join(targets)}|")
    lines += ['', '## 廃止した名前', '', ', '.join(f'`{t}`' for t in taxonomy['retired_tags']), '',
              '旧evaluation・records等は事業評価・組織報告まで含む意味を維持できないため、あいまいに新taskへ置換せず廃止しています。', '',
              '## 検索例', '', '```bash',
              'python tools/search_public_cards.py --kind integrated --hb43-only --tag task:points_assessment',
              'python tools/search_public_cards.py --source HB43 --individual-use relevant --tag task:split_interview',
              'python tools/search_public_cards.py --tag task:results_referral --tag topic:blood_pressure',
              'python tools/search_public_cards.py --kind all --individual-use undetermined', '```', '',
              '## 判定保留のカード', '']
    for c in cards:
        if 'individual:undetermined' in c['tags']:lines.append(f"- {link(c['evidence_id'])}：{c['classification']['reason']}")
    lines += ['', '## 更新・検証', '',
              '[定義台帳](tag_taxonomy.json)と[分類台帳](card_classifications.json)を編集して再生成します。本文・出典・条件は今回変更していません。'
              '全カードはreviewed=false、common=falseのままで、自動選択処理も変更していません。', '',
              '```bash', 'python tools/build_public_cards.py', 'python tools/validate_public_cards.py', 'python -m unittest discover -s tests', '```', '',
              '過去のレビュー依頼スライド・Excel内のタグ一覧は旧版です。現行定義には本ガイドを使用してください。', '']
    (root/'タグ整理ガイド.md').write_text('\n'.join(lines))
