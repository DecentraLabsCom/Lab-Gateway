import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import worker


class TestLocalModeEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = worker.APP.test_client()

    def test_requires_host(self):
        response = self.client.post('/api/hosts/local-mode', json={'enabled': True})
        self.assertEqual(response.status_code, 400)
        self.assertIn('host is required', response.get_data(as_text=True))

    def test_requires_enabled(self):
        response = self.client.post('/api/hosts/local-mode', json={'host': 'lab-ws-01'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('enabled is required', response.get_data(as_text=True))

    def test_host_not_found(self):
        response = self.client.post('/api/hosts/local-mode', json={'host': 'unknown', 'enabled': 'true'})
        self.assertEqual(response.status_code, 404)
        self.assertIn('not found', response.get_data(as_text=True))

    def test_enable_local_mode_writes_flag(self):
        fake_host = {'name': 'lab-ws-01', 'address': '127.0.0.1', 'winrm_user': 'user', 'winrm_pass': 'pass'}
        with patch.object(worker.HOSTS, 'get', return_value=fake_host), \
             patch('worker.write_remote_file') as mock_write, \
             patch('worker.remove_remote_file') as mock_remove:
            response = self.client.post('/api/hosts/local-mode', json={'host': 'lab-ws-01', 'enabled': True})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json.get('localModeEnabled'), True)
        mock_write.assert_called_once()
        mock_remove.assert_not_called()

    def test_disable_local_mode_removes_flag(self):
        fake_host = {'name': 'lab-ws-01', 'address': '127.0.0.1', 'winrm_user': 'user', 'winrm_pass': 'pass'}
        with patch.object(worker.HOSTS, 'get', return_value=fake_host), \
             patch('worker.write_remote_file') as mock_write, \
             patch('worker.remove_remote_file') as mock_remove:
            response = self.client.post('/api/hosts/local-mode', json={'host': 'lab-ws-01', 'enabled': False})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json.get('localModeEnabled'), False)
        mock_remove.assert_called_once()
        mock_write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
