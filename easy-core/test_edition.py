"""Run inside an isolated container, never against production data."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

if os.getenv('THREEWG_TEST_MODE') != '1':
    raise RuntimeError('Set THREEWG_TEST_MODE=1 in an isolated test container')
sys.path.insert(0, '/app')
import app as panel
from starlette.requests import Request
from api_keys_store import init_api_keys, create_api_key, delete_api_key


class EditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        panel.DB_PATH = Path(cls.temp.name) / 'panel.db'
        panel.init_db()
        init_api_keys(panel.DB_PATH)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_route_boundary(self):
        paths = {r.path for r in panel.app.routes}
        for path in ['/api/users', '/api/audit', '/api/migration', '/api/tools/ping', '/api/backups/auto', '/client/{client_id}/delete', '/clients']:
            with self.subTest(path=path):
                self.assertEqual(path in paths, not panel.IS_EASY)

    def test_integrations_and_peer_management_remain(self):
        paths = {r.path for r in panel.app.routes}
        for path in ['/api/apikeys', '/api/telegram', '/api/monitoring', '/metrics', '/api/peers', '/api/backups', '/api/dashboard', '/client/{client_id}/download']:
            self.assertIn(path, paths)

    def test_owner_auth(self):
        self.assertTrue(panel.authenticate_user(panel.PANEL_USER, panel.PANEL_PASSWORD)['is_admin'])
        self.assertIsNone(panel.authenticate_user(panel.PANEL_USER, 'wrong'))

    def test_database_user_is_core_only(self):
        with panel.db() as conn:
            conn.execute("INSERT OR REPLACE INTO panel_users (username, password_hash, role, created_at) VALUES (?, ?, 'user', 1)", ('edition-user', panel.password_hash('test-user-password')))
        self.assertEqual(panel.authenticate_user('edition-user', 'test-user-password') is not None, not panel.IS_EASY)
        token = panel.make_user_session('edition-user', 'user')
        self.assertEqual(panel.verify_user_session(token) is not None, not panel.IS_EASY)

    def test_api_key_lifecycle(self):
        key = create_api_key(panel.DB_PATH, 'integration-test')
        request = Request({'type': 'http', 'headers': [(b'x-api-key', key['token'].encode())]})
        self.assertTrue(panel.api_current_user(request)['is_admin'])
        delete_api_key(panel.DB_PATH, key['id'])
        self.assertIsNone(panel.api_current_user(request))

    def test_easy_background_backup_disabled(self):
        if panel.IS_EASY:
            self.assertIsNone(panel.api_maybe_run_auto_backup(force=True))
            panel.start_auto_backup_worker()
            self.assertFalse(panel.AUTO_BACKUP_THREAD_STARTED)


if __name__ == '__main__':
    unittest.main()
