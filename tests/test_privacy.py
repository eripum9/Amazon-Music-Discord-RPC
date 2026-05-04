"""Unit tests for privacy helpers."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from privacy import _privacy_keywords, _privacy_match


class TestPrivacyKeywords(unittest.TestCase):
    def test_comma_separated(self):
        config = {"privacy_blocked_keywords": "secret, hidden, private"}
        self.assertEqual(_privacy_keywords(config), ["secret", "hidden", "private"])

    def test_newline_separated(self):
        config = {"privacy_blocked_keywords": "secret\nhidden\nprivate"}
        self.assertEqual(_privacy_keywords(config), ["secret", "hidden", "private"])

    def test_mixed_separators(self):
        config = {"privacy_blocked_keywords": "word1,word2\nword3"}
        self.assertEqual(_privacy_keywords(config), ["word1", "word2", "word3"])

    def test_empty_string(self):
        config = {"privacy_blocked_keywords": ""}
        self.assertEqual(_privacy_keywords(config), [])

    def test_missing_key(self):
        self.assertEqual(_privacy_keywords({}), [])

    def test_whitespace_stripped(self):
        config = {"privacy_blocked_keywords": "  word  ,  other  "}
        self.assertEqual(_privacy_keywords(config), ["word", "other"])

    def test_lowercased(self):
        config = {"privacy_blocked_keywords": "MyKeyword"}
        self.assertEqual(_privacy_keywords(config), ["mykeyword"])


class TestPrivacyMatch(unittest.TestCase):
    def test_private_session(self):
        config = {"privacy_private_session": True}
        result = _privacy_match(config, title="Any Song", artist="Artist")
        self.assertTrue(result)
        self.assertIn("Private session", result)

    def test_private_session_disabled(self):
        config = {"privacy_private_session": False}
        result = _privacy_match(config, title="Any Song", artist="Artist")
        self.assertEqual(result, "")

    def test_keyword_in_title(self):
        config = {"privacy_blocked_keywords": "secret"}
        result = _privacy_match(config, title="My secret song")
        self.assertTrue(result)
        self.assertIn("secret", result)

    def test_keyword_in_artist(self):
        config = {"privacy_blocked_keywords": "private"}
        result = _privacy_match(config, artist="Private Artist")
        self.assertTrue(result)

    def test_keyword_in_album(self):
        config = {"privacy_blocked_keywords": "hidden"}
        result = _privacy_match(config, album="Hidden Collection")
        self.assertTrue(result)

    def test_no_match(self):
        config = {"privacy_blocked_keywords": "secret"}
        result = _privacy_match(config, title="Normal Song", artist="Public Artist", album="Open Album")
        self.assertEqual(result, "")

    def test_case_insensitive_match(self):
        config = {"privacy_blocked_keywords": "secret"}
        result = _privacy_match(config, title="My SECRET Song")
        self.assertTrue(result)

    def test_empty_config(self):
        result = _privacy_match({}, title="Any Song", artist="Artist")
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
