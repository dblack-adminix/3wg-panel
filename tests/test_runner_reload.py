import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('reload_update_runner', Path(__file__).resolve().parents[1] / 'scripts/reload_update_runner.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReloadTest(unittest.TestCase):
    def test_waits_until_updater_has_exited(self):
        with patch.object(module, 'process_identity', side_effect=['same', 'same', None]), patch.object(module.time, 'sleep') as sleep:
            module.wait_for_updater(123, 'same')
            self.assertEqual(sleep.call_count, 2)

    def test_reused_pid_does_not_block_reload(self):
        with patch.object(module, 'process_identity', return_value='other'), patch.object(module.time, 'sleep') as sleep:
            module.wait_for_updater(123, 'same')
            sleep.assert_not_called()

    def test_timeout_does_not_restart_running_updater(self):
        with patch.object(module, 'process_identity', return_value='same'):
            with self.assertRaises(TimeoutError):
                module.wait_for_updater(123, 'same', timeout=0)


if __name__ == '__main__':
    unittest.main()
