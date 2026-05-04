"""Unit tests for updater helpers (version parsing and changelog formatting)."""

import sys
import os
import unittest

# Allow importing from the project root without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from updater import _parse_version, _format_changelog


class TestParseVersion(unittest.TestCase):
    def test_standard_version(self):
        self.assertEqual(_parse_version("v2.1.0"), (2, 1, 0))

    def test_no_prefix(self):
        self.assertEqual(_parse_version("1.0.0"), (1, 0, 0))

    def test_single_component(self):
        self.assertEqual(_parse_version("v3"), (3,))

    def test_invalid_tag(self):
        self.assertEqual(_parse_version("not-a-version"), (0,))

    def test_empty_string(self):
        self.assertEqual(_parse_version(""), (0,))

    def test_comparison_newer(self):
        self.assertGreater(_parse_version("v2.2.0"), _parse_version("v2.1.0"))

    def test_comparison_equal(self):
        self.assertEqual(_parse_version("v1.0.0"), _parse_version("v1.0.0"))


class TestFormatChangelog(unittest.TestCase):
    def test_basic_changelog(self):
        body = (
            "Intro paragraph\n\n"
            "## What's New\n\n"
            "### New Features\n\n"
            "- Added diagnostics\n"
            "- Fixed privacy\n\n"
            "## Installation\n\n"
            "Download the installer."
        )
        result = _format_changelog(body)
        self.assertIn("Added diagnostics", result)
        self.assertIn("Fixed privacy", result)
        self.assertNotIn("Intro paragraph", result)
        self.assertNotIn("Download the installer", result)

    def test_empty_body(self):
        self.assertEqual(_format_changelog(""), "")

    def test_none_body(self):
        self.assertEqual(_format_changelog(None), "")

    def test_max_items(self):
        items = "\n".join(f"- Item {i}" for i in range(20))
        body = f"## What's New\n\n{items}"
        result = _format_changelog(body)
        lines = [l for l in result.splitlines() if l.strip().startswith("-")]
        self.assertLessEqual(len(lines), 5)

    def test_truncation(self):
        long_item = "- " + "x" * 200
        body = "## What's New\n\n" + "\n".join([long_item] * 10)
        result = _format_changelog(body)
        self.assertLessEqual(len(result), 600)

    def test_skip_headings_not_included(self):
        body = "## What's New\n\n### New Features\n\n- Great feature\n\n### Reliability\n\n- Stable"
        result = _format_changelog(body)
        self.assertNotIn("New Features", result)
        self.assertNotIn("Reliability", result)

    def test_stops_at_installation(self):
        body = "## What's New\n\n- Feature A\n\n## Installation\n\n- Install step"
        result = _format_changelog(body)
        self.assertIn("Feature A", result)
        self.assertNotIn("Install step", result)


if __name__ == "__main__":
    unittest.main()
