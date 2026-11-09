#!/usr/bin/env python3
"""Validate provenance and coverage of the public evidence corpus, offline."""
import csv
import hashlib
import json
import pathlib
import re
from collections import Counter
from urllib.parse import urlparse
from public_card_tags import load_taxonomy, load_classifications, validate_classifications

from integrated_public_cards import validate_integrated

ROOT = pathlib.Path(__file__).resolve().parents[1] / 'knowledge' / 'public'


def check(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    sources = json.loads((ROOT / 'sources.json').read_text())
    source_map = {s['source_id']: s for s in sources}
    check(len(source_map) == len(sources), 'Duplicate source ID')
    snapshots = {}
    for source in sources:
        path = ROOT / source['snapshot_path']
        raw = path.read_bytes()
        check(hashlib.sha256(raw).hexdigest() == source['snapshot_sha256'], f'Snapshot changed: {path}')
        rows = json.loads(raw)
        snapshots[source['source_id']] = {r['line']: r for r in rows}
        check([r['line'] for r in rows] == list(range(source['extracted_line_count'])), f'Missing extracted lines: {path}')
        check(not source['conflicting_lines'], f'Conflicting extraction: {path}')
        for r in rows:
            check(1 <= r['pdf_page'] <= r['pdf_page_end'] <= source['pdf_pages'], f'Invalid PDF page: {path}')
        check(source['visual_review_status'] == 'not_performed', 'Do not infer visual verification from text capture')

    summaries = json.loads((ROOT / 'evidence_cards.json').read_text())
    references = json.loads((ROOT / 'reference_cards.json').read_text())
    integrated = json.loads((ROOT / 'integrated_cards.json').read_text())
    integrated_specs = json.loads((ROOT / 'integrated_specs.json').read_text())
    cards = summaries + integrated + references
    validate_integrated(integrated, integrated_specs, cards)
    taxonomy = load_taxonomy(ROOT)
    ledger, _ = load_classifications(ROOT)
    classifications = validate_classifications(cards, taxonomy, ledger)
    for card in cards:
        entry = classifications[card['evidence_id']]
        check(card['tags'] == entry['tags'], f'Tag ledger mismatch: {card["evidence_id"]}')
        expected_classification = {k: entry[k] for k in ('reason', 'individual_scope', 'status')}
        expected_classification['taxonomy_version'] = taxonomy['version']
        check(card['classification'] == expected_classification, f'Classification metadata mismatch: {card["evidence_id"]}')
    ids = [c['evidence_id'] for c in cards]
    check(len(ids) == len(set(ids)), 'Duplicate evidence ID')
    known_ids = set(ids)
    provenance_records = cards + [dict(citation, evidence_id=c['evidence_id'] + '/' + citation['key'],
        reviewed=c['reviewed'], review_status=c['review_status'], common=c['common'],
        conditions=c['conditions'], related_evidence_ids=[], text=citation['source_excerpt'], card_type='source_excerpt')
        for c in integrated for citation in c['citations']]
    for card in provenance_records:
        cid = card['evidence_id']
        check(card['source_id'] in source_map, f'Unknown source: {cid}')
        source = source_map[card['source_id']]
        rows = snapshots[card['source_id']]
        loc = card['source_location']
        selected = [rows[n] for n in range(loc['extracted_line_start'], loc['extracted_line_end'] + 1)]
        expected = '\n'.join(r['text'] for r in selected)
        check(card['source_excerpt'] == expected, f'Excerpt mismatch: {cid}')
        check(hashlib.sha256(expected.encode()).hexdigest() == card['source_excerpt_sha256'], f'Excerpt hash mismatch: {cid}')
        check(loc['pdf_page_start'] == min(r['pdf_page'] for r in selected), f'Page start mismatch: {cid}')
        check(loc['pdf_page_end'] == max(r['pdf_page_end'] for r in selected), f'Page end mismatch: {cid}')
        check(card['url'] == source['url'] + f"#page={loc['pdf_page_start']}", f'URL mismatch: {cid}')
        check(urlparse(card['url']).netloc == 'www.mhlw.go.jp', f'Unexpected publisher URL: {cid}')
        check(card['edition'] == source['edition'], f'Edition mismatch: {cid}')
        check(card['reviewed'] is False and card['review_status'] == 'draft', f'Unrecorded expert approval: {cid}')
        check(card['common'] is False and len(card['conditions']) > 0, f'Unsafe unconditional card: {cid}')
        check(all(isinstance(x, str) and x.strip() for x in card['conditions']), f'Empty applicability note: {cid}')
        check(all(eid in known_ids for eid in card['related_evidence_ids']), f'Broken related card ID: {cid}')
        check(isinstance(card['text'], str) and card['text'].strip(), f'Empty text: {cid}')
        check('turn' not in card['url'], f'Temporary web citation leaked: {cid}')
        if card['card_type'] not in ('summary', 'integrated_summary'):
            check(card['text'] == expected, f'Reference text changed: {cid}')
        if card['card_type'] == 'qa':
            check('（答）' in expected, f'Question without answer: {cid}')

    coverage = json.loads((ROOT / 'coverage.json').read_text())
    check(coverage['integrated_card_count'] == len(integrated), 'Integrated count mismatch')
    check(coverage['summary_card_count'] == len(summaries), 'Summary count mismatch')
    check(coverage['reference_card_count'] == len(references), 'Reference count mismatch')
    for source in sources:
        sid = source['source_id']
        used = Counter()
        for card in references:
            if card['source_id'] == sid:
                loc = card['source_location']
                used.update(range(loc['extracted_line_start'], loc['extracted_line_end'] + 1))
        excluded = set(range(143)) if sid == 'HB43' else set(range(11)) if sid == 'QA20241025' else set()
        check(set(snapshots[sid]) - set(used) == excluded, f'Body coverage gap: {sid}')
        check(max(used.values()) == 1, f'Overlapping reference cards: {sid}')

    qa_starts = {n for n, r in snapshots['QA20241025'].items() if re.match(r'^問\s*[0-9０-９]+\s', r['text'])}
    qa_cards = {c['source_location']['extracted_line_start'] for c in references if c['card_type'] == 'qa'}
    check(qa_starts == qa_cards, 'Q&A question coverage mismatch')
    with (ROOT / 'summary_specs.tsv').open(newline='') as f:
        specs = list(csv.DictReader(f, delimiter='\t'))
    check(len(specs) == len(summaries), 'Editorial input count mismatch')
    print(f'OK: {len(sources)} sources, {len(summaries)} summaries, {len(integrated)} integrated, {len(references)} reference cards, {len(qa_cards)} Q&A.')
    print('Verified IDs, source URLs/editions, PDF page ranges, snapshot/excerpt hashes, extracted-line coverage, and draft-only state.')
    print(f'Verified explicit classifications for all {len(cards)} cards against {len(taxonomy["tags"])} tag definitions.')
    print('This check does not establish medical validity, current legal applicability, or visual/PDF layout accuracy.')


if __name__ == '__main__':
    main()
