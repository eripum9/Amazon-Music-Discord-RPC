"""Unit tests for config load/save behavior."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Provide a minimal stub for winreg so this test file works on non-Windows CI.
if "winreg" not in sys.modules:
    sys.modules["winreg"] = MagicMock()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config as cfg


class TestLoadConfig(unittest.TestCase):
    def test_defaults_when_no_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_path = os.path.join(tmpdir, "nonexistent.json")
            with patch.object(cfg, "CONFIG_PATH", fake_path):
                loaded = cfg.load_config()
        for key, value in cfg.DEFAULTS.items():
            self.assertEqual(loaded[key], value)

    def test_saved_values_override_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_path = os.path.join(tmpdir, "config.json")
            with open(fake_path, "w", encoding="utf-8") as f:
                json.dump({"song_link_enabled": True}, f)
            with patch.object(cfg, "CONFIG_PATH", fake_path):
                loaded = cfg.load_config()
        self.assertTrue(loaded["song_link_enabled"])

    def test_corrupt_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_path = os.path.join(tmpdir, "config.json")
            with open(fake_path, "w", encoding="utf-8") as f:
                f.write("not valid json {{{")
            with patch.object(cfg, "CONFIG_PATH", fake_path):
                loaded = cfg.load_config()
        for key, value in cfg.DEFAULTS.items():
            self.assertEqual(loaded[key], value)

    def test_all_default_keys_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_path = os.path.join(tmpdir, "nonexistent.json")
            with patch.object(cfg, "CONFIG_PATH", fake_path):
                loaded = cfg.load_config()
        missing = [k for k in cfg.DEFAULTS if k not in loaded]
        self.assertEqual(missing, [], f"Missing default keys: {missing}")


class TestSaveConfig(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_path = os.path.join(tmpdir, "config.json")
            with patch.object(cfg, "CONFIG_PATH", fake_path), \
                 patch.object(cfg, "CONFIG_DIR", tmpdir):
                data = {**cfg.DEFAULTS, "song_link_enabled": True}
                cfg.save_config(data)
                loaded = cfg.load_config()
        self.assertTrue(loaded["song_link_enabled"])

    def test_atomic_write(self):
        """save_config must not leave a .tmp file behind."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_path = os.path.join(tmpdir, "config.json")
            with patch.object(cfg, "CONFIG_PATH", fake_path), \
                 patch.object(cfg, "CONFIG_DIR", tmpdir):
                cfg.save_config(dict(cfg.DEFAULTS))
            tmp_files = [f for f in os.listdir(tmpdir) if f.endswith(".tmp")]
        self.assertEqual(tmp_files, [])


if __name__ == "__main__":
    unittest.main()
