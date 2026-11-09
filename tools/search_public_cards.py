#!/usr/bin/env python3
"""Search public evidence cards locally without sending source text to a model."""
import argparse
import json
from pathlib import Path
try:
    from .public_card_tags import load_taxonomy, resolve_tag
except ImportError:  # Direct CLI invocation.
    from public_card_tags import load_taxonomy, resolve_tag

ROOT = Path(__file__).resolve().parents[1] / 'knowledge' / 'public'


def search_cards(cards, taxonomy, *, query='', source=None, tags=(), individual_use=None, evidence_id=None):
    """AND across filters; OR within a legacy tag's replacement set."""
    tag_groups = [resolve_tag(tag, taxonomy) for tag in tags]
    if individual_use is not None:
        if individual_use not in ('relevant', 'not_relevant', 'undetermined'):
            raise ValueError(f'Invalid individual use: {individual_use}')
        tag_groups.append({f'individual:{individual_use}'})
    results = []
    for card in cards:
        if source and source not in {card['source_id'], *(c['source_id'] for c in card.get('citations', []))}:
            continue
        if evidence_id and card['evidence_id'] != evidence_id:
            continue
        if not all(set(card['tags']) & group for group in tag_groups):
            continue
        searchable = ' '.join([card['title'], card['text'], *card['conditions']]).casefold()
        if all(term.casefold() in searchable for term in query.split()):
            results.append(card)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('query', nargs='?', default='', help='All space-separated terms must match')
    parser.add_argument('--source', help='Source ID, for example HB43 or QA20241025')
    parser.add_argument('--tag', action='append', default=[], help='Tag or legacy alias; repeat for AND filtering')
    parser.add_argument('--individual-use', choices=('relevant', 'not_relevant', 'undetermined'),
                        help='Relevance to individual work, not approval or patient applicability')
    parser.add_argument('--id', help='Exact evidence ID')
    parser.add_argument('--kind', choices=('summary', 'detail', 'integrated', 'reference', 'all'), default='summary')
    parser.add_argument('--json', action='store_true', help='Print complete matching records as JSON')
    args = parser.parse_args()
    filenames = {'summary': ['evidence_cards.json', 'integrated_cards.json'],
                 'detail': ['evidence_cards.json'], 'integrated': ['integrated_cards.json'], 'reference': ['reference_cards.json'],
                 'all': ['evidence_cards.json', 'integrated_cards.json', 'reference_cards.json']}[args.kind]
    cards = [card for filename in filenames for card in json.loads((ROOT / filename).read_text())]
    try:
        results = search_cards(cards, load_taxonomy(ROOT), query=args.query, source=args.source,
                               tags=args.tag, individual_use=args.individual_use, evidence_id=args.id)
    except ValueError as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f'{len(results)} cards (all drafts; expert review pending)')
        for card in results:
            print(f"\n{card['evidence_id']}  {card['title']}\n{card['url']}")
            print('タグ：' + ', '.join(card['tags']))
            print('分類理由：' + card['classification']['reason'])
            if card['classification']['individual_scope']:
                print('個人業務での参照範囲：' + card['classification']['individual_scope'])
            if card['card_type'] in ('summary', 'integrated_summary'):
                print(card['text'])
                print('条件：' + ' / '.join(card['conditions']))
                for citation in card.get('citations', []):
                    print(f"出典 {citation['key']}：{citation['url']} — {citation['supports']}")
                if card.get('related_detail_ids'):
                    print('関連詳細カード：' + ', '.join(card['related_detail_ids']))


if __name__ == '__main__':
    main()
