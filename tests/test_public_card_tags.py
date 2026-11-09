import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from tools.public_card_tags import ROOT, load_taxonomy, load_classifications, validate_classifications
from tools.search_public_cards import search_cards


class PublicCardTagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = [c for filename in ('evidence_cards.json', 'integrated_cards.json', 'reference_cards.json')
                     for c in json.loads((ROOT / filename).read_text())]
        cls.taxonomy = load_taxonomy()
        cls.ledger, cls.entries = load_classifications()
        cls.by_id = {c['evidence_id']: c for c in cls.cards}

    def search(self, **kwargs):
        return {c['evidence_id'] for c in search_cards(self.cards, self.taxonomy, **kwargs)}

    def test_complete_classification_and_unchanged_draft_gate(self):
        self.assertEqual(len(self.cards), 865)
        validate_classifications(self.cards, self.taxonomy, self.ledger)
        for c in self.cards:
            self.assertEqual(c['tags'], self.entries[c['evidence_id']]['tags'])
            self.assertFalse(c['reviewed'])
            self.assertFalse(c['common'])
            self.assertTrue(c['conditions'])

    def test_personal_workflows_are_retrievable(self):
        examples = {
            'stratification': 'K_P2_3_004', 'eligibility': 'K_HB43_019',
            'referral': 'K_HB43_013', 'initial_interview': 'K_HB43_038',
            'goal_planning': 'K_P3_3_006', 'outcome_evaluation': 'K_QA20241025_026',
        }
        for task, cid in examples.items():
            with self.subTest(task=task):
                self.assertIn(cid, self.search(tags=[f'task:{task}'], individual_use='relevant'))

    def test_organization_history_and_incomplete_extraction(self):
        personal = self.search(individual_use='relevant')
        self.assertNotIn('K_ANN14_001', personal)
        self.assertNotIn('K_HB43_057', personal)
        self.assertTrue(all(c['evidence_id'] not in personal for c in self.cards
                            if c['card_type'] == 'historical_reference'))
        self.assertIn('REF_ALCOHOL_L00000', self.search(individual_use='undetermined'))
        for cid in self.search(individual_use='undetermined'):
            self.assertTrue(self.entries[cid]['reason'])
            self.assertEqual(self.entries[cid]['individual_scope'], '')

    def test_mixed_reference_has_explicit_personal_scope(self):
        c = self.by_id['REF_HB43_L00580']
        self.assertTrue({'use:organization', 'use:case_operations', 'individual:relevant'} <= set(c['tags']))
        self.assertIn('欠損', c['classification']['individual_scope'])

    def test_overbroad_topic_and_bp_duplication_removed(self):
        self.assertNotIn('topic:diet', self.by_id['K_HB43_015']['tags'])
        self.assertEqual(self.search(tags=['systolic_bp']), self.search(tags=['diastolic_bp']))
        self.assertEqual(self.search(tags=['systolic_bp']), self.search(tags=['topic:blood_pressure']))
        self.assertTrue(all('systolic_bp' not in c['tags'] for c in self.cards))

    def test_legacy_or_and_repeated_tag_and(self):
        for old, targets in self.taxonomy['legacy_aliases'].items():
            expected = set().union(*(self.search(tags=[target]) for target in targets))
            self.assertEqual(self.search(tags=[old]), expected)
        result = self.search(tags=['evaluation', 'use:case_operations'], individual_use='relevant')
        self.assertEqual(result, self.search(tags=['evaluation']) &
                         self.search(tags=['use:case_operations']) & self.search(individual_use='relevant'))
        self.assertEqual(self.search(tags=['individual:not_relevant'], individual_use='relevant'), set())

    def test_combined_source_text_and_id(self):
        result = self.search(tags=['topic:smoking'], query='喫煙 加算', source='P2_3',
                             individual_use='relevant', evidence_id='K_P2_3_003')
        self.assertEqual(result, {'K_P2_3_003'})
        self.assertEqual(self.search(evidence_id='K_P2_3_003', source='HB43'), set())

    def test_invalid_tags_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, 'Unknown tag'):
            self.search(tags=['topic:typo'])

    def assert_invalid_ledger(self, change):
        ledger = copy.deepcopy(self.ledger)
        change(ledger)
        with self.assertRaises(ValueError):
            validate_classifications(self.cards, self.taxonomy, ledger)

    def test_missing_duplicate_extra_ids_and_stale_basis(self):
        self.assert_invalid_ledger(lambda l: l['cards'].pop())
        self.assert_invalid_ledger(lambda l: l['cards'].append(l['cards'][0]))
        self.assert_invalid_ledger(lambda l: l['cards'][0].update(evidence_id='UNKNOWN'))
        self.assert_invalid_ledger(lambda l: l['cards'][0].update(basis_sha256='stale'))

    def test_unknown_duplicate_conflicting_tags_and_empty_reason(self):
        self.assert_invalid_ledger(lambda l: l['cards'][0]['tags'].append('unknown'))
        self.assert_invalid_ledger(lambda l: l['cards'][0]['tags'].append(l['cards'][0]['tags'][0]))
        self.assert_invalid_ledger(lambda l: l['cards'][0]['tags'].append('individual:undetermined'))
        self.assert_invalid_ledger(lambda l: l['cards'][0].update(reason=' '))
        self.assert_invalid_ledger(lambda l: l['cards'][0].update(individual_scope=''))

    def test_organization_cannot_be_marked_personal_by_flag_only(self):
        def change(l):
            row = next(r for r in l['cards'] if r['evidence_id'] == 'K_HB43_057')
            row['tags'] = ['individual:relevant', 'use:organization']
            row['individual_scope'] = 'incorrect'
        self.assert_invalid_ledger(change)

    def test_history_cannot_be_promoted_to_current_personal_use(self):
        historical_id = next(c['evidence_id'] for c in self.cards if c['card_type'] == 'historical_reference')
        def change(l):
            row = next(r for r in l['cards'] if r['evidence_id'] == historical_id)
            row['tags'] = ['individual:relevant', 'use:case_operations']
            row['individual_scope'] = 'incorrect'
        self.assert_invalid_ledger(change)

    def test_changed_body_or_conditions_requires_reclassification(self):
        for field, value in [('text', 'updated text'), ('conditions', ['updated condition'])]:
            with self.subTest(field=field):
                cards = copy.deepcopy(self.cards)
                cards[0][field] = value
                with self.assertRaisesRegex(ValueError, 'Stale'):
                    validate_classifications(cards, self.taxonomy, self.ledger)

    def test_cli_kind_default_reference_and_json(self):
        script = Path(__file__).resolve().parents[1] / 'tools/search_public_cards.py'
        def run(*args):
            return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)
        result = run('--individual-use', 'relevant', '--tag', 'task:stratification',
                     '--tag', 'use:case_operations', '--source', 'P2_3', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        cards = json.loads(result.stdout)
        self.assertTrue(cards)
        self.assertTrue(all(c['card_type'] in ('summary', 'integrated_summary') for c in cards))
        result = run('--kind', 'reference', '--individual-use', 'undetermined', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(c['card_type'] != 'summary' for c in json.loads(result.stdout)))
        self.assertEqual(run('--tag', 'typo').returncode, 2)


if __name__ == '__main__':
    unittest.main()
