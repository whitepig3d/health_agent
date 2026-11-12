"""Generate a blank professional review workbook for HB43-only cards."""
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'knowledge/public'
OUTPUT = ROOT / 'deliverables/professional_review/専門職レビュー票.xlsx'

def build():
    taxonomy = json.loads((PUBLIC / 'tag_taxonomy.json').read_text())
    cards = [c for f in ('evidence_cards.json', 'integrated_cards.json')
             for c in json.loads((PUBLIC / f).read_text())
             if 'individual:relevant' in c['tags'] and c['source_id'] == 'HB43'
             and (c['card_type'] == 'summary' or c['evidence_id'].startswith('I_HB43_'))]
    w = openpyxl.Workbook(); w.remove(w.active)
    def sheet(name, headers, rows):
        s = w.create_sheet(name); s.append(headers)
        for row in rows: s.append(row)
        s.freeze_panes = 'C2'; s.auto_filter.ref = s.dimensions
        for cell in s[1]:
            cell.fill = PatternFill('solid', fgColor='17365D'); cell.font = Font(color='FFFFFF', bold=True)
        for row in s.iter_rows(min_row=2):
            for cell in row: cell.alignment = Alignment(vertical='top', wrap_text=True)
        for col in s.columns: s.column_dimensions[col[0].column_letter].width = 32
        s.sheet_view.zoomScale = 85
        return s
    version = subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip()
    n = sum(c['card_type'] == 'summary' for c in cards)
    sheet('使い方', ['項目','説明'], [
        ['対象', f'HB43限定・individual:relevant：詳細{n}枚、統合{len(cards)-n}枚、計{len(cards)}枚'],
        ['対象版', version], ['タグ定義版',taxonomy['version']],
        ['出典条件','詳細はsource_id=HB43、統合はI_HB43系列。複数出典のI_SHG系列は対象外。'],
        ['手順','title・textをOK／要修正／判断保留で判定。内容がOKの場合だけタグを確認し、削除・置換・追加と理由を記入。修正後は再確認する。'],
        ['タグ別確認','taskごとの問い・該当IDを起点に、各カードの有用性と不足・重複・矛盾を記録。問いは必要に応じて具体化する。'],
        ['対象なし','該当0枚は対象範囲内での結果。情報不足と即断せず、必要なら調査依頼を記録する。'],
        ['必須としない工程','原文全件照合、条件・例外の網羅確認、全件二重レビュー、対象外カードの棚卸し'],
        ['状態','判定は未着手。記入しても原データのreviewed=false・common=falseは変更しない。'],
        ['記入','長文は数式バーまたは行の高さ調整で全文を確認。複数の指摘は指摘一覧に1件1行で記載。'],
        ['旧資料','既存スライドは旧対象・旧タグのため、本レビュー票と併用しない。'],
        ['作成日',datetime.now(ZoneInfo('Asia/Tokyo')).date().isoformat()]])
    def sources(c):
        return '\n'.join(dict.fromkeys(f"{x['source_id']} {x['url']} 抽出行{x['source_location']['extracted_line_start']}–{x['source_location']['extracted_line_end']}" for x in c.get('citations',[c])))
    sheet('対象カード',['ID','種別','title','text','conditions','tags','出典URL・範囲','本文SHA256','関連詳細カード'],[
        [c['evidence_id'],c['card_type'],c['title'],c['text'],'\n'.join(c['conditions']),', '.join(c['tags']),sources(c),hashlib.sha256(c['text'].encode()).hexdigest(),', '.join(c.get('related_detail_ids',[]))] for c in cards])
    s=sheet('カードレビュー',['ID','title','担当者','確認日','内容判定','問題箇所・理由','本文修正案・確認事項','タグ判定','削除タグ','置換（旧→新）','追加タグ','タグ変更理由','再確認判定','再確認者・日付'],[[c['evidence_id'],c['title'],None,None,'未着手',None,None,'未着手',None,None,None,None,'未着手',None] for c in cards])
    for col in ('E','H','M'):
        dv=DataValidation(type='list',formula1='"未着手,OK,要修正,判断保留"');s.add_data_validation(dv);dv.add(f'{col}2:{col}{s.max_row}')
    sheet('タグ別レビュー',['タグ・組合せ','業務上の問い','担当者・日付','該当カードID','有用性の判定と理由','不足・重複・矛盾','対応案（タグ追加／本文修正／新規／調査）','対応状況'],[
        [t['id'],f"{t['label']}：{t['include']}を、どの条件・手順で判断・実施するか？",None,'\n'.join(c['evidence_id'] for c in cards if t['id'] in c['tags']) or '対象内0枚',None,None,None,'未着手'] for t in taxonomy['tags'] if t['id'].startswith('task:')])
    sheet('指摘一覧',['指摘ID','カードID又はタグ','担当者・日付','問題箇所','理由','修正案・確認事項','編集担当の対応','再確認結果','再確認者・日付'],[])
    sheet('タグ定義',['タグ','日本語名','付与条件','除外・注意','代表ID'],[[t['id'],t['label'],t['include'],t['exclude'],', '.join(t['example_ids'])] for t in taxonomy['tags']])
    for name in ('対象カード','タグ別レビュー'):
        s=w[name]
        for row in range(2,s.max_row+1): s.row_dimensions[row].height=110
    w['対象カード'].column_dimensions['D'].width=100
    w['使い方'].column_dimensions['B'].width=110
    w.save(OUTPUT)
    check=openpyxl.load_workbook(OUTPUT)
    assert check['対象カード'].max_row == len(cards)+1
    assert check['タグ別レビュー'].max_row == 19
    for i,c in enumerate(cards,2): assert check['対象カード'].cell(i,4).value == c['text']
    print(f'{OUTPUT}: {n} detail + {len(cards)-n} integrated; 18 tasks; {len(taxonomy["tags"])} definitions')

if __name__ == '__main__': build()
