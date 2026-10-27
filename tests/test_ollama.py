import json
import unittest
from unittest.mock import MagicMock, patch
from health_agent import Ollama

class OllamaTests(unittest.TestCase):
    def response(self, result):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(result).encode()
        return opener

    @patch('health_agent.urllib.request.build_opener')
    def test_request(self, build):
        build.return_value = self.response({'done': True, 'done_reason': 'stop', 'message': {'content': '{"findings": []}'}})
        self.assertEqual(Ollama().generate('テスト', 'synthetic'), '{"findings": []}')
        request = build.return_value.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, 'http://127.0.0.1:11434/api/chat')
        self.assertEqual(payload['model'], 'gemma3:4b')
        self.assertFalse(payload['stream'])
        self.assertEqual(payload['format'], 'json')

    @patch('health_agent.urllib.request.build_opener')
    def test_truncation(self, build):
        build.return_value = self.response({'done': True, 'done_reason': 'length', 'message': {'content': '{}'}})
        with self.assertRaises(ValueError): Ollama().generate('test', 'synthetic')

    @patch.dict('os.environ', {}, clear=True)
    @patch('health_agent.urllib.request.build_opener')
    def test_real_data_gate(self, build):
        with self.assertRaises(ValueError): Ollama().generate('test', 'real_pseudonymized')
        build.assert_not_called()

    def test_timeout(self):
        with self.assertRaises(ValueError): Ollama(timeout=0)
