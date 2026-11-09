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
        self.assertEqual(sum(c['theme_id'] == 12 for c in self.integrated), 4)
        for c in self.integrated:
            self.assertEqual(c['text'], render_text(c['sections']))
            self.assertTrue(c['related_detail_ids'])
            self.assertFalse(c['reviewed'])
            self.assertFalse(c['common'])

    def test_secondary_source_filter_and_combined_filters(self):
        # First source is P2_3; HB43 appears only in the additional citations.
        card = next(c for c in self.integrated if c['evidence_id'] == 'I_SHG_01')
        self.assertNotEqual(card['source_id'], 'HB43')
        found = search_cards(self.integrated, self.taxonomy, source='HB43',
                             tags=['task:stratification', 'use:case_operations'],
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
        specs[0]['theme_id'] = 2
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
        for kind, expected, count in [('detail', {'summary'}, 136),
                                      ('integrated', {'integrated_summary'}, 22),
                                      ('summary', {'summary', 'integrated_summary'}, 158),
                                      ('all', {'summary', 'integrated_summary', 'source_excerpt', 'qa', 'historical_reference'}, 865)]:
            with self.subTest(kind=kind):
                result = subprocess.run([sys.executable, str(script), '--kind', kind, '--json'],
                                        capture_output=True, text=True, check=True)
                cards = json.loads(result.stdout)
                self.assertEqual(len(cards), count)
                self.assertEqual({c['card_type'] for c in cards}, expected)


if __name__ == '__main__':
    unittest.main()
