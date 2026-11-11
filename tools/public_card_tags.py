"""Explicit editorial classification for the public corpus (not clinical approval)."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'knowledge' / 'public'
INDIVIDUAL = {f'individual:{x}' for x in ('relevant', 'not_relevant', 'undetermined')}
PERSONAL = {'use:guidance', 'use:case_operations'}


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
            if not tags & PERSONAL or not scope.strip() or c['card_type'] == 'historical_reference':
                raise ValueError(f'Invalid individual relevance: {cid}')
        elif 'individual:not_relevant' in tags and (tags & PERSONAL or scope):
            raise ValueError(f'Non-relevant card has personal use: {cid}')
        elif 'individual:undetermined' in tags and scope:
            raise ValueError(f'Undetermined card must not claim an established individual scope: {cid}')
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
    if tag in {d['id'] for d in taxonomy['tags']}:
        return {tag}
    if tag in taxonomy['legacy_aliases']:
        return set(taxonomy['legacy_aliases'][tag])
    raise ValueError(f'Unknown tag: {tag}')


def render_tag_guide(cards, root=ROOT):
    """Render counts and definitions from the same inputs used by the builder."""
    taxonomy = load_taxonomy(root)
    ledger, entries = load_classifications(root)
    summary = [c for c in cards if c['card_type'] in ('summary', 'integrated_summary')]
    reference = [c for c in cards if c['card_type'] not in ('summary', 'integrated_summary')]
    counts = [Counter(t for c in group for t in c['tags']) for group in (summary, reference)]
    def cell(value):
        return value.replace('|', '\\|').replace('\n', ' ')
    def link(cid):
        card = next(c for c in cards if c['evidence_id'] == cid)
        target = ('統合カード一覧.md' if card['card_type'] == 'integrated_summary' else '根拠カード一覧.md' if card['card_type'] == 'summary'
                  else f'references/{card["source_id"]}.md')
        return f'[{cid}]({target}#{cid.lower()})'
    lines = [
        '# 根拠カードのタグ整理・検索ガイド', '',
        f'分類版：{taxonomy["version"]}。要点{len(summary)}枚・原文参照{len(reference)}枚、計{len(cards)}枚（要点には統合カードを含む）を対象に、5軸・{len(taxonomy["tags"])}タグを定義しています。', '',
        '**「個人業務の参照候補」は、特定の本人への適用可・医学的承認済みを意味しません。** '
        '全カードは専門職レビュー前です。用途の分類、本人への適用条件（`conditions`）、レビュー状態（`reviewed`）を別々に確認してください。', '',
        '## 個人業務で使うための読み方', '',
        '- `individual:relevant`：本人への指導又は個別ケース運用の具体的根拠を含む参照候補。',
        '- `individual:not_relevant`：組織業務・制度背景・旧制度履歴等。個人業務の直接参照対象外。不要な資料という意味ではありません。',
        '- `individual:undetermined`：抽出不足などで個人業務の参照範囲を確定できない。原本等を確認するまで保留。',
        '- 指導内容は `use:guidance`、階層化・面接要件・個人評価等は `use:case_operations`、保険者や機関の事務は `use:organization`。混在カードには複数付与します。',
        '- 個人向けの説明文を探すなら `use:guidance`、担当者の手順確認なら `use:case_operations` を指定します。原文の混在カードは `classification.individual_scope` に記した部分を参照します。',
        '- 同一カードに複数タグが付きます。話題・用途別の件数合計は総カード数と一致しません。', '',
        '## 現行分類で解消した過不足', '',
        '|従来の問題|再定義|', '|---|---|',
        '|出典抜粋に語があるだけで付与|カードIDごとに趣旨を判断した分類台帳を生成元にする。正規表現による自動確定を廃止|',
        '|個人指導と組織の事務が混在|用途と個人業務との関連を独立した軸にする|',
        '|血圧タグ2種が同じ条件|`topic:blood_pressure` に統合。収縮期・拡張期は本文で検索|',
        '|階層化・受診勧奨・初回面接等のタグ不足|業務段階の11タグを追加。服薬・フレイルも話題として追加|',
        '|評価・同意・記録の意味が広い|個人評価／算定／事業評価、同意／情報保護、個人記録／保存／国等への報告を分離|',
        '|食事・運動などが職種名や付随語から過剰付与|要点の中心や原文の具体的な記載に限定。章の話題を断片カードへ一律継承しない|', '',
        '心電図・眼底・貧血など専用の話題タグを設けていない項目は、`task:assessment`、`task:results_explanation`、`task:referral` と本文検索を組み合わせます。'
        '年齢・服薬状態などは話題や用途タグだけで機械判定しません。', '',
        '## 定義と付与件数', '',
        '以下は編集定義であり、語句の自動一致条件ではありません。代表例のリンク先で適用条件と出典を確認できます。', '',
    ]
    headings = {'use': '用途', 'individual': '個人業務との関連判定', 'task': '業務段階',
                'topic': '健康・生活の話題', 'operation': '実施方法・制度事務'}
    for namespace, heading in headings.items():
        lines += [f'### {heading}', '', '|タグ・名称|付与条件|除外・注意|要点|原文参照|代表例|',
                  '|---|---|---|---:|---:|---|']
        for d in taxonomy['tags']:
            if d['id'].startswith(namespace + ':'):
                lines.append(f'|`{d["id"]}` {cell(d["label"])}|{cell(d["include"])}|{cell(d["exclude"])}|'
                             f'{counts[0][d["id"]]}|{counts[1][d["id"]]}|{", ".join(link(cid) for cid in d["example_ids"])}|')
        lines.append('')
    lines += ['## 判定保留のカード', '', '|カード|保留理由|', '|---|---|']
    for c in cards:
        if 'individual:undetermined' in c['tags']:
            lines.append(f'|{link(c["evidence_id"])}|{cell(entries[c["evidence_id"]]["reason"])}|')
    lines += ['', '## 代表的な分類の確認', '', '|カード|分類上の判断|', '|---|---|']
    for cid in ('K_HB43_015', 'K_HB43_013', 'K_QA20241025_021', 'K_HB43_057',
                'K_ANN14_001', 'REF_HB43_L00580'):
        row = entries[cid]
        lines.append(f'|{link(cid)}|{cell(row["reason"])} {cell(row["individual_scope"])}|')
    lines += ['', '## 旧タグとの対応', '',
              '旧名は検索時の別名として受け付けます。分割先のいずれかに一致するOR検索です。'
              '再分類で過剰付与を除いたため、旧版と同じ検索結果件数になる保証はありません。生成カードには新タグだけを格納します。', '',
              '|旧名|検索する新タグ（OR）|', '|---|---|']
    for old, targets in taxonomy['legacy_aliases'].items():
        lines.append(f'|`{old}`|{" / ".join(f"`{tag}`" for tag in targets)}|')
    lines += ['', '## 検索方法', '',
        'リポジトリのルートで実行します。既定は詳細要点と統合カード。`--kind integrated` は統合のみ、`--kind detail` は詳細要点のみ、`--kind reference` は原文のみ、`--kind all` は全種類です。'
        '`--tag` は繰り返すとAND検索、旧名の分割先はその指定の内側でOR検索になります。'
        '用途・出典・ID・キーワードもAND条件です。不明なタグはエラーにします。'
        'キーワードは空白区切りのAND検索で、タイトル・本文・条件を対象とします（要点の出典抜粋や分類理由は対象外）。', '',
        '```bash',
        '# 個人業務で参照できる要点',
        'python tools/search_public_cards.py --individual-use relevant',
        '# 階層化の運用を確認',
        'python tools/search_public_cards.py --individual-use relevant --tag use:case_operations --tag task:stratification',
        '# 禁煙の本人向け支援内容',
        'python tools/search_public_cards.py --individual-use relevant --tag use:guidance --tag topic:smoking',
        '# 個人の評価を手引きから検索（原文も含む）',
        'python tools/search_public_cards.py --individual-use relevant --tag task:outcome_evaluation --source HB43 --kind all',
        '# 抽出不足で保留した原文',
        'python tools/search_public_cards.py --individual-use undetermined --kind reference',
        '# 旧タグ名と本文を組み合わせる',
        'python tools/search_public_cards.py 収縮期 --tag systolic_bp',
        '```', '',
        '## 編集入力と更新', '',
        '- [定義台帳](tag_taxonomy.json)：版、定義、日本語名、付与・除外条件、代表例、旧名対応。',
        '- [全カードの分類台帳](card_classifications.json)：全IDのタグ、分類理由、個人業務で参照する範囲、編集草案状態、本文等のハッシュ。',
        '- カードの `classification` にも理由・参照範囲・編集草案状態・分類版を出力します。'
        '`classification.status=editorial_draft` は専門職レビューを意味しません。',
        '- 本文・条件・出典・版・カード種別を変えた場合は分類を再確認します。未登録ID、重複、余分なID、古いハッシュがあると再生成を停止します。'
        'ハッシュだけを書き換えて確認を済ませたことにしないでください。',
        '- 原文が複数用途を含む場合は用途を併記し、個人業務の参照範囲を具体的に記します。'
        '前後カードが必要ならその旨も残します。図表の目視確認がないことと、本文から用途を分類できることは別です。',
        '- 旧制度履歴は現行の個人業務の参照候補にしません。医学・制度の承認フラグ、条件、アプリの自動選択処理は変更していません。', '',
        '```bash', 'python tools/build_public_cards.py', 'python tools/validate_public_cards.py',
        'python -m unittest discover -s tests', '```', '',
        'このガイドは生成物です。定義・分類台帳を更新してビルダーを実行すると、カードと件数表・保留一覧を再生成します。'
        '検証は構造・出典整合性を確認するもので、分類の医学的妥当性や最新法令への適用を承認するものではありません。', '',
        '関連：[根拠カード集](README.md)／[要点カード一覧](根拠カード一覧.md)／[要点カード補完記録](要点カード補完記録.md)', '',
    ]
    (root / 'タグ整理ガイド.md').write_text('\n'.join(lines))
