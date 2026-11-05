#!/usr/bin/env python3
"""Search public evidence cards locally without sending source text to a model."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'knowledge' / 'public'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('query', nargs='?', default='', help='All space-separated terms must match')
    parser.add_argument('--source', help='Source ID, for example HB43 or QA20241025')
    parser.add_argument('--tag', help='Exact topic tag')
    parser.add_argument('--id', help='Exact evidence ID')
    parser.add_argument('--kind', choices=('summary', 'reference', 'all'), default='summary')
    parser.add_argument('--json', action='store_true', help='Print complete matching records as JSON')
    args = parser.parse_args()
    filenames = {'summary': ['evidence_cards.json'], 'reference': ['reference_cards.json'],
                 'all': ['evidence_cards.json', 'reference_cards.json']}[args.kind]
    cards = [card for filename in filenames for card in json.loads((ROOT / filename).read_text())]
    results = []
    for card in cards:
        if args.source and card['source_id'] != args.source:
            continue
        if args.tag and args.tag not in card['tags']:
            continue
        if args.id and card['evidence_id'] != args.id:
            continue
        searchable = ' '.join([card['title'], card['text'], *card['conditions']]).casefold()
        if all(term.casefold() in searchable for term in args.query.split()):
            results.append(card)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f'{len(results)} cards (all drafts; expert review pending)')
        for card in results:
            print(f"\n{card['evidence_id']}  {card['title']}\n{card['url']}")
            if card['card_type'] == 'summary':
                print(card['text'])
                print('条件：' + ' / '.join(card['conditions']))


if __name__ == '__main__':
    main()
