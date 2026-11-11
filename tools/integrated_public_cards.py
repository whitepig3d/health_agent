"""Build multi-source editorial summaries without changing detailed cards."""

SECTIONS = ('必要情報', '判断・手順', '例外・中止・保留', '結論・記録')


def render_text(sections):
    return '\n\n'.join(f'【{s["heading"]}】\n{s["text"]}' for s in sections)


def build_integrated(specs, make_card, references, summaries):
    known = {c['evidence_id']: c for c in summaries}
    result = []
    for spec in specs:
        cid = spec['evidence_id']
        citations = []
        for entry in spec['sources']:
            c = make_card(cid, entry['source_id'], entry['line_start'], entry['line_end'], spec['title'])
            citations.append({**{k: c[k] for k in ('source_id', 'url', 'edition', 'source_location',
                                                   'source_excerpt', 'source_excerpt_sha256')},
                              'key': entry['key'], 'supports': entry['supports']})
        first = spec['sources'][0]
        c = make_card(cid, first['source_id'], first['line_start'], first['line_end'],
                      spec['title'], 'integrated_summary', render_text(spec['sections']), spec['conditions'])
        c.update(citations=citations, sections=spec['sections'], theme_id=spec['theme_id'],
                 related_detail_ids=spec['related_detail_ids'], editorial_date='2026-11-09')
        if spec.get('source_policy'):
            c['source_policy'] = spec['source_policy']
            c['editorial_date'] = spec['editorial_date']
        if not set(c['related_detail_ids']) <= known.keys():
            raise ValueError(f'Unknown detail card: {cid}')
        ref_ids = []
        for ref in references:
            loc = ref['source_location']
            if any(ref['source_id'] == s['source_id'] and
                   loc['extracted_line_start'] <= s['line_end'] and
                   loc['extracted_line_end'] >= s['line_start'] for s in spec['sources']):
                ref_ids.append(ref['evidence_id'])
        c['related_evidence_ids'] = c['related_detail_ids'] + ref_ids
        c['editorial_note'] = ('複数原文を判断手順として再構成した編集草案。citationsが全出典、単一出典欄は第一出典。'
                               '記録項目には判断を追跡するための編集上の推奨を含み、一律の法定必須項目とはしない。')
        result.append(c)
    return result


def validate_integrated(cards, specs, all_cards):
    """Validate the authored procedure, its sources and detail links as one unit."""
    known = {c['evidence_id']: c for c in all_cards}
    if len(specs) != len(cards) or len({s['evidence_id'] for s in specs}) != len(specs):
        raise ValueError('Integrated spec count or duplicate ID')
    expected = {s['evidence_id']: s for s in specs}
    if set(expected) != {c['evidence_id'] for c in cards}:
        raise ValueError('Integrated IDs mismatch')
    if {s['theme_id'] for s in specs} != set(range(1, 20)):
        raise ValueError('Integrated themes must cover 1–19')
    for c in cards:
        s = expected[c['evidence_id']]
        def require(ok, message):
            if not ok:
                raise ValueError(f'{message}: {c["evidence_id"]}')
        require(c['card_type'] == 'integrated_summary', 'Integrated kind')
        require(c['title'] == s['title'] and c['conditions'] == s['conditions'] and
                c['theme_id'] == s['theme_id'], 'Integrated spec mismatch')
        require(c['sections'] == s['sections'] and c['text'] == render_text(s['sections']), 'Integrated text mismatch')
        require(tuple(x['heading'] for x in c['sections']) == SECTIONS, 'Missing procedure section')
        require(c['related_detail_ids'] == s['related_detail_ids'] and bool(c['related_detail_ids']), 'Detail links mismatch')
        require(all(e in known and known[e]['card_type'] == 'summary' for e in c['related_detail_ids']), 'Invalid detail link')
        require(len(c['citations']) == len(s['sources']) > 0, 'Citation count')
        keys = {x['key'] for x in c['citations']}
        require(len(keys) == len(c['citations']), 'Duplicate citation key')
        used = set()
        for section in c['sections']:
            require(section['text'].strip() and section['source_keys'] and
                    set(section['source_keys']) <= keys, 'Uncited procedure section')
            used.update(section['source_keys'])
        require(used == keys, 'Unused citation')
        for actual, source in zip(c['citations'], s['sources']):
            require(actual['key'] == source['key'] and actual['supports'] == source['supports'] and
                    actual['source_id'] == source['source_id'] and
                    actual['source_location']['extracted_line_start'] == source['line_start'] and
                    actual['source_location']['extracted_line_end'] == source['line_end'], 'Citation spec mismatch')
        expected_refs = [ref['evidence_id'] for ref in all_cards
                         if ref['card_type'] not in ('summary', 'integrated_summary') and
                         any(ref['source_id'] == source['source_id'] and
                             ref['source_location']['extracted_line_start'] <= source['line_end'] and
                             ref['source_location']['extracted_line_end'] >= source['line_start']
                             for source in s['sources'])]
        require(c['related_evidence_ids'] == c['related_detail_ids'] + expected_refs, 'Reference links mismatch')
        if s.get('source_policy') == 'HB43_only':
            require(c.get('source_policy') == 'HB43_only', 'Missing HB43 policy')
            require(all(x['source_id'] == 'HB43' for x in c['citations']), 'Foreign source in HB43 card')
            require(all(known[e]['source_id'] == 'HB43'
                        for e in c['related_detail_ids']), 'HB43 detail closure')
            require(set(x['key'] for x in c['citations']) == set(c['related_detail_ids']), 'Unexplained HB43 citation')
            for citation in c['citations']:
                detail = known[citation['key']]
                require(citation['source_location'] == detail['source_location'] and
                        citation['source_excerpt_sha256'] == detail['source_excerpt_sha256'], 'HB43 detail provenance mismatch')
            for section in c['sections']:
                require(bool(section.get('detail_ids')) and
                        set(section['detail_ids']) <= set(c['related_detail_ids']), 'HB43 explanation missing')
        first = c['citations'][0]
        require(all(c[k] == first[k] for k in ('source_id', 'url', 'edition', 'source_location',
                                              'source_excerpt', 'source_excerpt_sha256')), 'Primary citation mismatch')


def render_integrated_guide(cards, all_cards, root):
    mapping = {c['evidence_id']: c for c in all_cards}
    lines = ['# 統合カード一覧', '',
             f'編集日：2026年11月11日。複数出典版22枚とHB43限定版16枚、統合カード{len(cards)}枚。既存の詳細要点136枚にHB43要点10枚を追加。原文参照707枚は維持しています。', '',
             '全カードは専門職レビュー前の草案（reviewed=false、common=false）です。'
             '本文は収録版の原文を組み合わせた編集文であり、医療上の診断・承認を意味しません。'
             '記録項目には判断過程を追跡するための編集上の推奨を含みます。', '',
             '各カードは必要情報、判断・手順、例外・中止・保留、結論・記録で構成します。'
             'テーマ12は検査領域ごとに4枚へ分割しました。全体像と個別の算定判定は業務上の問いが異なるため別カードとし、'
             'その問いに必要な条件は重複して本文に記載しています。', '',
             '## テーマと業務上の問い', '', '|テーマ|統合カード|', '|---|---|']
    for c in cards:
        lines.append(f'|{c["theme_id"]}|[{c["evidence_id"]}：{c["title"]}](#{c["evidence_id"].lower()})|')
    lines += ['', '## 検索・更新', '',
              '既定の要点検索は詳細と統合の両方を検索します。出典フィルターは統合カードの全出典を対象にします。', '',
              '```bash', 'python tools/search_public_cards.py --kind integrated --tag task:stratification',
              'python tools/search_public_cards.py --kind integrated --source P2_FB --tag task:referral',
              'python tools/search_public_cards.py --id I_SHG_16',
              'python tools/search_public_cards.py --kind detail', '```', '',
              '編集入力は[integrated_specs.json](integrated_specs.json)、出力は[integrated_cards.json](integrated_cards.json)。'
              '分類は[全カードの分類台帳](card_classifications.json)に明示しています。'
              '各出典の範囲・抜粋・版・ハッシュと本文・関連詳細カードを検証し、本文や出典変更時は分類の再確認を要求します。'
              '単一出典の互換フィールドは第一出典を示し、全根拠は`citations`に保持します。', '',
              '収録原文は保存済みPDF抽出テキストです。原本の図表の目視照合や外部通知の全文を新たに確認したという意味ではありません。'
              '未評価時の詳細な実績報告要件など、収録原文が外部通知の確認を求める箇所は保険者確認として明示しています。', '']
    for c in cards:
        lines += [f'<a id="{c["evidence_id"].lower()}"></a>', f'## {c["evidence_id"]} — {c["title"]}', '',
                  '**状態：専門職レビュー未実施**', '', c['text'], '',
                  '**適用条件**：' + ' / '.join(c['conditions']), '',
                  '**タグ**：' + ', '.join(c['tags']), '', '**分類理由**：' + c['classification']['reason'], '',
                  '**個人業務の参照範囲**：' + (c['classification']['individual_scope'] or '組織業務のため該当なし'), '',
                  '### 出典と補完した条件', '', '|キー|原文・範囲|裏付ける内容|', '|---|---|---|']
        for source in c['citations']:
            loc = source['source_location']
            lines.append(f'|{source["key"]}|[{source["source_id"]} PDF {loc["pdf_page_start"]}–{loc["pdf_page_end"]}]({source["url"]}) '
                         f'／抽出行{loc["extracted_line_start"]}–{loc["extracted_line_end"]}／{source["edition"]}|{source["supports"]}|')
        lines += ['', '**関連詳細カード**：' + ', '.join(
            f'[{eid}](根拠カード一覧.md#{eid.lower()})' for eid in c['related_detail_ids']), '',
            '**関連原文参照**：' + ', '.join(
                f'[{eid}](references/{mapping[eid]["source_id"]}.md#{eid.lower()})'
                for eid in c['related_evidence_ids'] if eid not in c['related_detail_ids']), '']
    (root / '統合カード一覧.md').write_text('\n'.join(lines))


def render_hb43_guide(cards, all_cards, root):
    selected = [c for c in cards if c.get('source_policy') == 'HB43_only']
    details = {c['evidence_id']: c for c in all_cards if c['card_type'] == 'summary'}
    lines = ['# HB43限定版統合カードと説明用要点', '',
             '2026年11月11日。既存の複数出典版22枚は維持し、レビュー対象だった17テーマに対応するHB43限定版を追加しました。I_HB43_06（腹囲・体重）はI_HB43_05へ統合し、現在は16枚です。', '',
             '各限定版の全出典はHB43です。関連する詳細要点もすべてHB43かつindividual:relevantに限定します。'
             'ただしHB43が他資料を参照する判断はその範囲を明記しています。受診勧奨は医師による個別判断の手順、高齢者は65～74歳の制度区分と支援実施に範囲を絞り、他資料の数値・臨床条件を持ち込みません。', '',
             '詳細要点K_HB43_063～072を10枚追加。既存詳細を含む説明用要点の本文と統合本文を編集照合しました。'
             '参照の閉鎖性は機械検証しますが、意味上の網羅性は専門職の承認を得たものではありません。全カードは草案です。', '',
             '今回のレビュー候補はHB43関連詳細64枚＋限定版16枚＝80枚です。通常の --source HB43 は旧複数出典版も含むため、限定版だけの検索には --hb43-only を使います。', '',
             '```bash', 'python tools/search_public_cards.py --kind integrated --hb43-only --individual-use relevant',
             'python tools/search_public_cards.py --kind detail --source HB43 --individual-use relevant', '```', '',
             '前回のレビュー依頼スライド・Excelは71枚を対象とした旧版であり、今回の80枚とは対象が異なります。', '',
             '## 追加した詳細要点', '']
    for n in range(63,73):
        c=details[f'K_HB43_{n:03}'];lines += [f"### {c['evidence_id']} — {c['title']}", '', c['text'], '', f"[原本]({c['url']})", '']
    lines += ['## 限定版と説明用要点の対応', '']
    for c in selected:
        lines += [f"## {c['evidence_id']} — {c['title']}", '', c['text'], '',
                  '説明用要点：'+', '.join(f"[{e}](根拠カード一覧.md#{e.lower()})" for e in c['related_detail_ids']), '',
                  f"[全出典・分類](統合カード一覧.md#{c['evidence_id'].lower()})", '']
    (root/'HB43限定統合カード.md').write_text('\n'.join(lines))
