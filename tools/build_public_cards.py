#!/usr/bin/env python3
"""Rebuild draft evidence cards offline from captured public source text.

No network access, clinical approval, or runtime selection is performed.
Source snapshots, summary_specs.tsv and integrated_specs.json are the editorial inputs.
"""
import csv
import hashlib
import json
import pathlib
import re
import unicodedata
from collections import Counter
from public_card_tags import apply_classifications, render_tag_guide
from integrated_public_cards import build_integrated, validate_integrated, render_integrated_guide

ROOT = pathlib.Path(__file__).resolve().parents[1] / 'knowledge' / 'public'
DATE = '2026-11-05'
SOURCES = json.loads((ROOT/'sources.json').read_text())
ROWS = {s['source_id']: json.loads((ROOT/s['snapshot_path']).read_text()) for s in SOURCES}

def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()

def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')

SOURCE_MAP={s['source_id']:s for s in SOURCES}

def excerpt(sid,a,b):
    return '\n'.join(r['text'] for r in ROWS[sid] if a<=r['line']<=b)

def make_card(cid,sid,a,b,title,kind='source_excerpt',text=None,conditions=None):
    rows=[r for r in ROWS[sid] if a<=r['line']<=b]
    assert rows and rows[0]['line']==a and rows[-1]['line']==b,(cid,a,b)
    src=SOURCE_MAP[sid]
    raw=excerpt(sid,a,b)
    p1=min(r['pdf_page'] for r in rows);p2=max(r['pdf_page_end'] for r in rows)
    c=dict(evidence_id=cid,title=title,source_id=sid,url=src['url']+f'#page={p1}',edition=src['edition'],
       section=f'{title}／PDF {p1}–{p2}ページ',publisher=src['publisher'],data_kind='public_source',
       card_type=kind,text=raw if text is None else text,source_excerpt=raw,
       source_location={'pdf_page_start':p1,'pdf_page_end':p2,'extracted_line_start':a,'extracted_line_end':b},
       source_excerpt_sha256=digest(raw),tags=[],
       common=False,conditions=conditions or ['当該資料・章の対象、例外、脚注、適用年度を原本で確認した上で専門職が適用を判断する。'],
       reviewed=False,review_scope='資料作成段階。専門職の医学・制度レビューおよび原本図表との目視照合は未実施。',
       review_status='draft',priority=10 if kind=='summary' else 100,accessed_on=DATE,
       extraction_notes=['PDF抽出テキスト。外字、改行、ページ末尾、図表の行列関係には未校正の箇所がある。'],
       related_evidence_ids=[])
    if any(p in src['sparse_text_pages'] for p in range(p1,p2+1)):
        c['extraction_notes'].append('参照範囲にテキストが少ないページがある。画像中の内容を収録できていない可能性がある。')
    return c

REFERENCES=[]
def blocks(sid, starts):
    starts=sorted(set(starts)); end=ROWS[sid][-1]['line']+1
    # Merge heading-only fragments forward without dropping any captured lines.
    if sid != 'QA20241025':
        i=0
        while i+1<len(starts):
            raw=excerpt(sid,starts[i],starts[i+1]-1)
            if len(raw)<80 and '。' not in raw:
                starts.pop(i+1)
            else:
                i+=1
    for i,a in enumerate(starts):
        b=(starts[i+1] if i+1<len(starts) else end)-1
        raw=excerpt(sid,a,b)
        if not raw.strip():continue
        first=next((r['text'] for r in ROWS[sid] if a<=r['line']<=b and len(r['text'].strip())>3),'資料')
        title=first[:110]
        REFERENCES.append(make_card(f'REF_{sid}_L{a:05}',sid,a,b,title))

# 本編は章節単位。親見出しだけの独立カードを作らず、最初の子節に含める。
rows=ROWS['HB43']; starts=[143,180]
for r in rows:
    if r['line']<181 or r['line'] in (3472,5084):continue
    if re.match(r'^[1-8]-\d+(?:-\d+)?\s',r['text']):starts.append(r['line'])
starts=sorted(set(starts))
starts=[a for i,a in enumerate(starts) if not(i+1<len(starts) and starts[i+1]-a<=2)]
# 表紙・目次は原文スナップショットにのみ保持。付録の旧制度は現行ルールから分離。
history=next(r['line'] for r in rows if r['line']>5691 and '第三期' in r['text'])
starts.append(history)
blocks('HB43',starts)
for c in REFERENCES:
    if c['source_id']=='HB43' and c['source_location']['extracted_line_start']>=history:
        c['card_type']='historical_reference';c['conditions']=['第三期・第二期の改訂履歴を調べる用途に限定。現行の指導ルールとして適用しない。']

# Q&Aは問と答を一体で保存し、同じ問番号を編・分野・行位置で識別する。
rows=ROWS['QA20241025'];starts=[r['line'] for r in rows if re.match(r'^問\s*[0-9０-９]+\s',r['text'])]
blocks('QA20241025',starts)
for c in REFERENCES:
    if c['source_id']!='QA20241025':continue
    a=c['source_location']['extracted_line_start']
    stage='第4期追加Q&A' if a<321 else '第4期向け再編集Q&A'
    head=''
    for r in rows:
        if r['line']>a:break
        if re.match(r'^[1-6１-６][.．]\s*特定|^[1-6１-６][.．]\s*(?:外部|補助|その他)',r['text']):head=r['text']
    q=c['source_excerpt'].split('（答）')[0]
    c['title']=stage+'／'+head+'／'+re.sub(r'\s+',' ',q)[:100]
    c['section']=f"{stage}／{head}／PDF {c['source_location']['pdf_page_start']}–{c['source_location']['pdf_page_end']}ページ"
    c['card_type']='qa'

# 補助資料は自然な章節を優先。長い図表等はページ単位の原文参照として分ける。
for sid,rows in ROWS.items():
    if sid in ('HB43','QA20241025'):continue
    natural=[0]
    for r in rows:
        t=unicodedata.normalize('NFKC',r['text'])
        if re.match(r'^(?:第[1-9一二三四五六七八九十]+章|[1-9][－-][0-9]+\s|\([1-9][0-9]?\)\s*[^0-9]|別紙[1-9])',t) and len(t)<100:
            natural.append(r['line'])
    natural=sorted(set(natural))
    starts=[]
    for i,a in enumerate(natural):
        b=natural[i+1] if i+1<len(natural) else rows[-1]['line']+1
        if i+1<len(natural) and b-a<=2:continue
        starts.append(a)
        chunk=[r for r in rows if a<=r['line']<b]
        # 大きな節は見開き程度のページ範囲で分け、前後参照を後段で付ける。
        if sum(len(r['text']) for r in chunk)>6500:
            anchor=chunk[0]['pdf_page']
            for r in chunk:
                if r['pdf_page']>=anchor+2:
                    starts.append(r['line']);anchor=r['pdf_page']
    blocks(sid,sorted(set([0]+starts)))

for sid in ROWS:
    group=[c for c in REFERENCES if c['source_id']==sid]
    for i,c in enumerate(group):
        c['related_evidence_ids']=[x['evidence_id'] for x in group[max(0,i-1):i+2] if x is not c]
        c['extraction_notes'].append('節・ページ境界で参照カードを分けている。文や脚注が続く場合は前後カードも併読する。')

SUMMARIES=[]
with (ROOT/'summary_specs.tsv').open(newline='') as f:
    for row in csv.DictReader(f, delimiter='\t'):
        sid=row['source_id'];a=int(row['line_start']);b=int(row['line_end'])
        cid=row['evidence_id']
        card=make_card(cid,sid,a,b,row['title'],'summary',row['text'],[row['conditions']])
        card['related_evidence_ids']=[c['evidence_id'] for c in REFERENCES
            if c['source_id']==sid and c['source_location']['extracted_line_start']<=b
            and c['source_location']['extracted_line_end']>=a]
        card['editorial_note']='textは出典を要約した編集文。conditionsは適用条件と誤用防止の編集注記であり、原文の逐語引用ではない。source_excerptは抽出テキスト。'
        SUMMARIES.append(card)

for card in REFERENCES:
    if card['card_type'] not in ('qa','historical_reference'):
        loc=card['source_location']
        # Continuation text must not masquerade as an independently authored rule.
        card['title']=f"{SOURCE_MAP[card['source_id']]['title']}／PDF {loc['pdf_page_start']}–{loc['pdf_page_end']}／{card['title']}"

INTEGRATED_SPECS = json.loads((ROOT/'integrated_specs.json').read_text())
INTEGRATED = build_integrated(INTEGRATED_SPECS, make_card, REFERENCES, SUMMARIES)
ALL_CARDS = SUMMARIES + INTEGRATED + REFERENCES
validate_integrated(INTEGRATED, INTEGRATED_SPECS, ALL_CARDS)
apply_classifications(ALL_CARDS, ROOT)

write_json(ROOT/'evidence_cards.json',SUMMARIES)
write_json(ROOT/'integrated_cards.json',INTEGRATED)
render_integrated_guide(INTEGRATED, ALL_CARDS, ROOT)
write_json(ROOT/'reference_cards.json',REFERENCES)

def md_card(card, include_excerpt=False):
    loc=card['source_location']
    result=[f"## {card['evidence_id']} — {card['title']}", '',
        f"出典：[原本PDF {loc['pdf_page_start']}–{loc['pdf_page_end']}ページ]({card['url']}) ｜ {card['edition']}", '',
        '**状態：専門職レビュー未実施**', '', ('````text\n'+card['text']+'\n````') if include_excerpt else card['text'], '',
        '**適用条件・編集注記**：'+' / '.join(card['conditions']), '']
    result += ['**用途・話題タグ**：' + ', '.join(card['tags']), '',
        '**分類理由**：' + card['classification']['reason'], '']
    if card['classification']['individual_scope']:
        result += ['**個人業務での参照範囲**：' + card['classification']['individual_scope'], '']
    if card['related_evidence_ids']:
        if include_excerpt:
            result+=['前後参照：'+', '.join(card['related_evidence_ids']),'']
        else:
            result+=['原文参照：'+', '.join(f"[{eid}](references/{card['source_id']}.md#{eid.lower()})" for eid in card['related_evidence_ids']),'']
    return '\n'.join(result)

index=['# 根拠カード一覧', '',
    f'確認日：{DATE}。要点カード {len(SUMMARIES)}枚、原文参照カード {len(REFERENCES)}枚。', '',
    '要点カードは本文を要約した編集文です。原文参照カードはPDFの抽出テキストで、図表・画像・脚注の完全再現ではありません。全カードが専門職レビュー前の草案です。', '',
    '出典：厚生労働省。出典資料を抽出・編集して作成したもので、厚生労働省が作成・承認したカードではありません。', '',
    '## 資料別の原文参照', '', '|資料ID|資料|参照カード数|', '|---|---|---:|']
counts=Counter(c['source_id'] for c in REFERENCES)
for source in SOURCES:
    sid=source['source_id']
    index.append(f"|{sid}|[{source['title']}](references/{sid}.md)|{counts[sid]}|")
    rendered=[f"# {source['title']}", '', f"[原本PDF]({source['url']}) ｜ {source['edition']} ｜ 確認日 {DATE}", '',
      source['attribution'], '', '全カードがレビュー前。図表の行列・外字・画像中の情報は原本PDFで確認してください。前後カードに続く文・脚注があります。', '']
    for c in REFERENCES:
        if c['source_id']==sid:
            rendered += [f"<a id=\"{c['evidence_id'].lower()}\"></a>", md_card(c,True)]
    (ROOT/'references'/f'{sid}.md').write_text('\n'.join(rendered))
index += ['', '## 要点カード', '']
for c in SUMMARIES:index += [f'<a id="{c["evidence_id"].lower()}"></a>', md_card(c)]
(ROOT/'根拠カード一覧.md').write_text('\n'.join(index))
report={
    'as_of':DATE,'source_count':len(SOURCES),'summary_card_count':len(SUMMARIES),
    'integrated_card_count':len(INTEGRATED),'reference_card_count':len(REFERENCES),'qa_card_count':sum(c['card_type']=='qa' for c in REFERENCES),
    'expert_reviewed_card_count':0,'visual_reviewed_source_count':0,
    'sources':[]}
for source in SOURCES:
    sid=source['source_id'];covered=set()
    for c in REFERENCES:
        if c['source_id']==sid:
            loc=c['source_location'];covered.update(range(loc['extracted_line_start'],loc['extracted_line_end']+1))
    excluded=set(range(143)) if sid=='HB43' else set(range(11)) if sid=='QA20241025' else set()
    captured={r['line'] for r in ROWS[sid]}
    report['sources'].append(dict(source_id=sid,pdf_pages=source['pdf_pages'],
        captured_lines=len(captured),expected_extracted_lines=source['extracted_line_count'],
        missing_extracted_lines=source['missing_lines'],reference_cards=counts[sid],
        uncovered_body_lines=sorted(captured-covered-excluded),
        excluded_front_matter_lines=sorted(excluded),sparse_text_pages=source['sparse_text_pages']))
write_json(ROOT/'coverage.json',report)
render_tag_guide(ALL_CARDS, ROOT)
print(f"Built {len(SUMMARIES)} summaries + {len(INTEGRATED)} integrated + {len(REFERENCES)} reference cards from {len(SOURCES)} sources")

