# MIT License - Copyright (c) 2026 eripum9

import importlib.util
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location("evidence", Path(__file__).parents[1] / "check_pr_evidence.py")
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)
SHA = "a" * 40
BODY = f"""## Scope
Fix playback behavior.
## Validation
Tested commit: {SHA}
Commands: python -m unittest
Results: all tests passed
## Regression Evidence
Before the change playback failed; after the change it passes.
## Platform Checks
Windows checked locally.
## Untested / Limitations
macOS was not available.
"""


def event(body=BODY, author="contributor", count=1):
    return {"pull_request": {"body": body, "user": {"login": author}, "head": {"sha": SHA}, "changed_files": count}}


def file(name, status="modified", **extra):
    return {"filename": name, "status": status, **extra}


class EvidenceTests(unittest.TestCase):
    def test_valid_paged_runtime_change(self):
        self.assertEqual([], evidence.validate(event(count=2), [[file("Windows/main.py")], [file("Shared/tests/test_playback.py", "added")]]))

    def test_empty_template_and_comments_fail(self):
        body = "\n".join(f"## {s}\n<!-- example -->\nTODO" for s in evidence.SECTIONS)
        errors = evidence.validate(event(body), [file("README.md")])
        self.assertTrue(any("Scope" in e for e in errors))
        self.assertTrue(any("Tested commit" in e for e in errors))

    def test_wrong_or_short_commit_and_missing_fields_fail(self):
        for body in (BODY.replace(SHA, "b" * 40), BODY.replace(SHA, "aaaa"), BODY.replace("Commands: python -m unittest", "Commands: TODO")):
            self.assertTrue(evidence.validate(event(body), [file("README.md")]))

    def test_runtime_requires_corresponding_non_deleted_test(self):
        for test in (file("Windows/tests/test_a.py", "removed"), file("Windows/tests/test_a.py", "renamed", previous_filename="old.py"), file("Windows/tests/README.md"), file("MacOS/tests/test_a.py")):
            self.assertTrue(any("Windows runtime" in e for e in evidence.validate(event(count=2), [file("Windows/main.py"), test])))
        self.assertTrue(any("Shared runtime" in e for e in evidence.validate(event(count=2), [file("Shared/playback.py"), file("Windows/tests/test_a.py")])))

    def test_old_renamed_runtime_path_counts(self):
        errors = evidence.validate(event(), [file("docs/old.py", "renamed", previous_filename="MacOS/main.py")])
        self.assertTrue(any("MacOS runtime" in e for e in errors))

    def test_na_only_for_non_runtime_with_reason(self):
        body = BODY.replace("Before the change playback failed; after the change it passes.", "N/A: Documentation-only wording change, no runtime behavior changed.")
        self.assertEqual([], evidence.validate(event(body), [file("README.md")]))
        self.assertTrue(any("Regression" in e for e in evidence.validate(event(body, count=2), [file("Windows/main.py"), file("Windows/tests/test_a.py")])))
        self.assertTrue(any("Regression" in e for e in evidence.validate(event(body), [file(".github/scripts/check.py")])))
        self.assertTrue(any("Regression" in e for e in evidence.validate(event(body.replace("Documentation-only wording change, no runtime behavior changed.", "TODO")), [file("README.md")])))

    def test_dependabot_exception_is_narrow(self):
        bot = event("", "dependabot[bot]")
        self.assertEqual([], evidence.validate(bot, [file("Windows/requirements-dev.txt")]))
        for files in ([file("Windows/main.py")], [file(".github/workflows/test.yml")], [file("requirements.txt", "renamed", previous_filename="Windows/main.py")]):
            self.assertTrue(evidence.validate(bot, files))
        self.assertTrue(evidence.validate(event("", "another[bot]"), [file("Windows/requirements.txt")]))

    def test_invalid_files_fail_closed(self):
        for files in ([], {}, [{"filename": "Windows/main.py"}], [file("new.py", "renamed")]):
            with self.assertRaises(ValueError):
                evidence.validate(event(), files)

    def test_changed_file_count_fails_closed_before_dependabot_exemption(self):
        for count in (None, True, -1, 2, 3001):
            errors = evidence.validate(event("", "dependabot[bot]", count), [file("requirements.txt")])
            self.assertTrue(any("changed_files" in error or "reports" in error for error in errors))
        missing = event()
        del missing["pull_request"]["changed_files"]
        self.assertTrue(evidence.validate(missing, [file("README.md")]))

    def test_workflow_bootstrap_source_guard(self):
        workflow = (Path(__file__).parents[2] / "workflows" / "pr-evidence.yml").read_text(encoding="utf-8")
        self.assertIn('if [ -f .github/scripts/check_pr_evidence.py ]; then', workflow)
        self.assertIn('[ "$HEAD_REPOSITORY" = "$REPOSITORY" ] && [ "$PR_AUTHOR" = "$REPOSITORY_OWNER" ]', workflow)
        self.assertIn("if: steps.bootstrap.outputs.checkout_head == 'true'", workflow)
        self.assertIn("ref: ${{ github.event.pull_request.base.sha }}", workflow)
        self.assertIn("ref: ${{ github.event.pull_request.head.sha }}", workflow)
        self.assertIn("exit 1", workflow)


if __name__ == "__main__":
    unittest.main()
