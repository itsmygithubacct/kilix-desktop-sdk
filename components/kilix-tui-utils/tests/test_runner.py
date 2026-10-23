"""The suite must not inherit a live desktop's storage or launch settings."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('tui_test_runner', Path(__file__).with_name('run.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def test_sandbox_removes_live_settings_and_preserves_explicit_dependencies(self):
        paths = []
        def invoke(argv, **kwargs):
            env = kwargs['env']
            self.assertNotIn('KILIX_ROLLOUT_RESUME_GAP', env)
            self.assertNotIn('KILIX_CONFIG_HOME', env)
            self.assertNotIn('CODEX_HOME', env)
            self.assertNotIn('KITTY_LISTEN_ON', env)
            self.assertEqual(env['KILIX_HOME'], '/explicit/host')
            self.assertEqual(env['GPU_TERMINAL_SOURCE_HOME'], '/explicit/sources')
            self.assertEqual(env['PYTHONPATH'], '/explicit/bindings')
            self.assertNotEqual(env['HOME'], '/operator')
            for key in ('HOME', 'TMPDIR', 'XDG_CONFIG_HOME', 'KILIX_STORAGE_HOME'):
                path = Path(env[key])
                self.assertTrue(path.is_dir())
                paths.append(path)
            self.assertLess(len(env['TMPDIR'].encode()), 60)
            return subprocess.CompletedProcess(argv, 0, '', '')
        with patch.dict(os.environ, {
            'HOME': '/operator', 'TMPDIR': '/long/' + 'x' * 120,
            'KILIX_HOME': '/explicit/host', 'GPU_TERMINAL_SOURCE_HOME': '/explicit/sources',
            'PYTHONPATH': '/explicit/bindings', 'KILIX_ROLLOUT_RESUME_GAP': '999',
            'KILIX_CONFIG_HOME': '/operator/config', 'CODEX_HOME': '/operator/agents',
            'KITTY_LISTEN_ON': 'unix:/operator/live.sock',
        }, clear=True), patch.object(runner.os, 'listdir', return_value=['test_probe.py']), \
                patch.object(runner.sys, 'argv', ['run.py']), \
                patch.object(runner.subprocess, 'run', side_effect=invoke), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(), 0)
            self.assertEqual(os.environ['HOME'], '/operator')
        self.assertTrue(paths)
        self.assertTrue(all(not path.exists() for path in paths))

    def test_child_failure_is_not_reported_as_success(self):
        with patch.object(runner.os, 'listdir', return_value=['test_probe.py']), \
                patch.object(runner.sys, 'argv', ['run.py']), \
                patch.object(runner.subprocess, 'run', return_value=
                             subprocess.CompletedProcess([], 1, '', 'failed')), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(), 1)


if __name__ == '__main__':
    unittest.main()
