import json
import unittest
from health_agent import summary, approve, plan

class Model:
    model_id = 'test-only'
    def generate(self, prompt, data_kind):
        return json.dumps({'findings': [{'text': '変化', 'evidence_refs': ['F0']}], 'questions': []})

def data():
    return dict(subject_id='DEMO', data_kind='synthetic', exams=[dict(exam_id=str(i), exam_date=f'{2023+i}-01-01', measurements=[dict(source_id=f'F{i}', code='weight', value=70+i, unit='kg', method='scale', condition='same')]) for i in range(2)])

class Tests(unittest.TestCase):
    def test_difference(self):
        self.assertEqual(summary(data(), Model())['trends'][0]['delta'], 1)
    def test_not_comparable(self):
        d=data(); d['exams'][1]['measurements'][0]['condition']='other'
        self.assertIsNone(summary(d, Model())['trends'][0]['delta'])
    def test_mixed_subject(self):
        d=data(); d['exams'][0]['subject_id']='other'
        with self.assertRaises(ValueError): summary(d, Model())
    def test_approval(self):
        s=summary(data(), Model())
        with self.assertRaises(ValueError): plan(s, [], Model())
        s=approve(s, 'reviewer', '確認済み'); s['facts'][0]['value']=99
        with self.assertRaises(ValueError): plan(s, [], Model())
    def test_missing_evidence(self):
        s=approve(summary(data(), Model()), 'reviewer', '確認済み')
        with self.assertRaises(ValueError): plan(s, [], Model())
