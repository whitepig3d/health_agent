"""Regression tests for multi-source provenance and procedure-card generation."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.integrated_public_cards import render_text, validate_integrated
from tools.public_card_tags import ROOT, basis_hash, load_classifications, load_taxonomy, validate_classifications
from tools.search_public_cards import search_cards


class IntegratedCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.integrated = json.loads((ROOT / 'integrated_cards.json').read_text())
        cls.specs = json.loads((ROOT / 'integrated_specs.json').read_text())
        cls.all_cards = [c for filename in ('evidence_cards.json', 'integrated_cards.json', 'reference_cards.json')
                         for c in json.loads((ROOT / filename).read_text())]
        cls.taxonomy = load_taxonomy()
        cls.ledger, _ = load_classifications()

    def test_themes_and_detail_provenance_are_complete(self):
        validate_integrated(self.integrated, self.specs, self.all_cards)
        self.assertEqual({c['theme_id'] for c in self.integrated}, set(range(1, 20)))
        self.assertEqual(sum(c['theme_id'] == 12 for c in self.integrated), 5)
        for c in self.integrated:
            self.assertEqual(c['text'], render_text(c['sections']))
            self.assertTrue(c['related_detail_ids'])
            self.assertFalse(c['reviewed'])
            self.assertFalse(c['common'])

    def test_hb43_only_explanation_closure(self):
        selected = [c for c in self.integrated if c.get('source_policy') == 'HB43_only']
        self.assertEqual(len(selected), 16)
        details = {c['evidence_id']: c for c in self.all_cards}
        for c in selected:
            self.assertTrue(all(x['source_id'] == 'HB43' for x in c['citations']))
            for eid in c['related_detail_ids']:
                self.assertEqual(details[eid]['source_id'], 'HB43')
                self.assertIn('individual:relevant', details[eid]['tags'])
            self.assertEqual(set(c['related_detail_ids']), {x['key'] for x in c['citations']})
        cards = copy.deepcopy(self.integrated)
        card = next(c for c in cards if c.get('source_policy') == 'HB43_only')
        card['sections'][0]['detail_ids'] = []
        specs = copy.deepcopy(self.specs)
        next(s for s in specs if s['evidence_id'] == card['evidence_id'])['sections'] = card['sections']
        card['text'] = render_text(card['sections'])
        with self.assertRaisesRegex(ValueError, 'explanation missing'):
            validate_integrated(cards, specs, self.all_cards)

    def test_secondary_source_filter_and_combined_filters(self):
        # First source is P2_3; HB43 appears only in the additional citations.
        card = next(c for c in self.integrated if c['evidence_id'] == 'I_SHG_01')
        self.assertNotEqual(card['source_id'], 'HB43')
        found = search_cards(self.integrated, self.taxonomy, source='HB43',
                             tags=['task:stratification', 'individual:relevant'],
                             individual_use='relevant', query='判定不能', evidence_id='I_SHG_01')
        self.assertEqual([c['evidence_id'] for c in found], ['I_SHG_01'])
        self.assertEqual(search_cards([card], self.taxonomy, source='ANN14'), [])

    def test_secondary_source_and_links_invalidate_classification(self):
        for field in ('citations', 'related_detail_ids', 'sections'):
            with self.subTest(field=field):
                cards = copy.deepcopy(self.all_cards)
                c = next(c for c in cards if c['evidence_id'] == 'I_SHG_01')
                original = basis_hash(c)
                if field == 'citations':
                    c[field][-1]['source_excerpt'] += ' changed'
                elif field == 'sections':
                    c[field][0]['text'] += ' changed'
                else:
                    c[field].pop()
                self.assertNotEqual(basis_hash(c), original)
                with self.assertRaisesRegex(ValueError, 'Stale'):
                    validate_classifications(cards, self.taxonomy, self.ledger)

    def test_missing_theme_or_orphaned_sources_fail(self):
        specs = copy.deepcopy(self.specs)
        for spec in specs:
            if spec['theme_id'] == 1:
                spec['theme_id'] = 2
        with self.assertRaisesRegex(ValueError, 'themes'):
            validate_integrated(self.integrated, specs, self.all_cards)
        cards = copy.deepcopy(self.integrated)
        cards[0]['citations'].pop()
        with self.assertRaisesRegex(ValueError, 'Citation count'):
            validate_integrated(cards, self.specs, self.all_cards)

    def test_modified_body_and_missing_reference_link_fail(self):
        for change, message in ((lambda c: c.update(text='changed'), 'text mismatch'),
                                (lambda c: c['related_evidence_ids'].pop(), 'Reference links mismatch')):
            cards = copy.deepcopy(self.integrated)
            change(cards[0])
            with self.assertRaisesRegex(ValueError, message):
                validate_integrated(cards, self.specs, self.all_cards)

    def test_validator_rejects_changed_secondary_excerpt_even_with_new_ledger_hash(self):
        # A refreshed classification hash must never substitute for raw-source verification.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in ROOT.iterdir():
                (root / path.name).symlink_to(path, target_is_directory=path.is_dir())
            cards = copy.deepcopy(self.integrated)
            cards[0]['citations'][-1]['source_excerpt'] += ' incorrect excerpt'
            ledger = copy.deepcopy(self.ledger)
            next(r for r in ledger['cards'] if r['evidence_id'] == cards[0]['evidence_id'])['basis_sha256'] = basis_hash(cards[0])
            for filename, data in [('integrated_cards.json', cards), ('card_classifications.json', ledger)]:
                (root / filename).unlink()
                (root / filename).write_text(json.dumps(data, ensure_ascii=False))
            script = Path(__file__).resolve().parents[1] / 'tools/validate_public_cards.py'
            code = ("import pathlib,runpy,sys; sys.path.insert(0,str(pathlib.Path(sys.argv[1]).parent)); "
                    "ns=runpy.run_path(sys.argv[1]); ns['main'].__globals__['ROOT']=pathlib.Path(sys.argv[2]); ns['main']()")
            result = subprocess.run([sys.executable, '-c', code, str(script), str(root)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Excerpt mismatch', result.stderr)

    def test_cli_kinds_separate_and_default_includes_both(self):
        script = Path(__file__).resolve().parents[1] / 'tools/search_public_cards.py'
        for kind, expected, count in [('detail', {'summary'}, 146),
                                      ('integrated', {'integrated_summary'}, 38),
                                      ('summary', {'summary', 'integrated_summary'}, 184),
                                      ('all', {'summary', 'integrated_summary', 'source_excerpt', 'qa', 'historical_reference'}, 891)]:
            with self.subTest(kind=kind):
                result = subprocess.run([sys.executable, str(script), '--kind', kind, '--json'],
                                        capture_output=True, text=True, check=True)
                cards = json.loads(result.stdout)
                self.assertEqual(len(cards), count)
                self.assertEqual({c['card_type'] for c in cards}, expected)


if __name__ == '__main__':
    unittest.main()
