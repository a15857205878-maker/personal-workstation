import tempfile
import unittest
from pathlib import Path
from pairing import load_token, save_token


class PairingTest(unittest.TestCase):
    def test_restart_keeps_token(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'pairing.json'
            first = load_token(path)
            self.assertGreaterEqual(len(first), 32)
            self.assertEqual(load_token(path), first)

    def test_preserve_existing_link_and_explicit_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'pairing.json'
            old = 'A' * 32
            save_token(path, old)
            self.assertEqual(load_token(path), old)
            save_token(path, 'B' * 32)
            self.assertEqual(load_token(path), 'B' * 32)

    def test_corrupt_credentials_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'pairing.json'
            for value in ('{}', '{', '{"token":"short"}', '{"token":123}'):
                path.write_text(value, encoding='utf-8')
                with self.assertRaises(ValueError):
                    load_token(path)
                self.assertEqual(path.read_text(encoding='utf-8'), value)
