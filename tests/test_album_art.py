"""Unit tests for album art metadata helpers."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from album_art import _clean_title


class TestCleanTitle(unittest.TestCase):
    def test_explicit_bracket(self):
        self.assertEqual(_clean_title("Song [Explicit]"), "Song")

    def test_feat_parens(self):
        self.assertEqual(_clean_title("Song (feat. Someone)"), "Song")

    def test_ft_parens(self):
        self.assertEqual(_clean_title("Song (ft. Someone)"), "Song")

    def test_no_change_needed(self):
        self.assertEqual(_clean_title("Normal Song"), "Normal Song")

    def test_multiple_brackets(self):
        result = _clean_title("Song [Explicit] [Remastered]")
        self.assertEqual(result, "Song")

    def test_case_insensitive_feat(self):
        self.assertEqual(_clean_title("Song (Feat. Artist)"), "Song")

    def test_empty_string(self):
        self.assertEqual(_clean_title(""), "")

    def test_whitespace_trimmed(self):
        self.assertEqual(_clean_title("  Song  [Explicit]  "), "Song")


if __name__ == "__main__":
    unittest.main()
