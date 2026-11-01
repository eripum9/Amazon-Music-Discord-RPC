# MIT License - Copyright (c) 2026 eripum9

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class QualityRulesetTests(unittest.TestCase):
    def load_ruleset(self, name):
        return json.loads((ROOT / ".github" / "rulesets" / name).read_text(encoding="utf-8"))

    def test_ci_has_no_owner_or_app_bypass(self):
        policy = self.load_ruleset("required-ci.json")
        self.assertEqual(policy["enforcement"], "active")
        self.assertEqual(policy["conditions"]["ref_name"], {"include": ["refs/heads/master"], "exclude": []})
        self.assertEqual(policy["bypass_actors"], [])
        rules = {rule["type"]: rule.get("parameters", {}) for rule in policy["rules"]}
        self.assertIn("deletion", rules)
        self.assertIn("non_fast_forward", rules)
        self.assertEqual(rules["pull_request"]["required_approving_review_count"], 0)
        self.assertTrue(rules["pull_request"]["required_review_thread_resolution"])
        checks = rules["required_status_checks"]
        self.assertTrue(checks["strict_required_status_checks_policy"])
        required = {check["context"]: check["integration_id"] for check in checks["required_status_checks"]}
        for context in ("windows-tests", "macos-tests", "dependency-audit", "dependency-review",
                        "codeql (python)", "codeql (actions)", "runtime-integration", "contribution-evidence"):
            self.assertEqual(required[context], 15368)
        self.assertEqual(required["CodeQL"], 57789)

    def test_owner_exception_is_review_only_and_pr_only(self):
        policy = self.load_ruleset("required-review.json")
        self.assertEqual(policy["enforcement"], "active")
        self.assertEqual(policy["bypass_actors"], [
            {"actor_id": 127331524, "actor_type": "User", "bypass_mode": "pull_request"}
        ])
        self.assertEqual(len(policy["rules"]), 1)
        self.assertEqual(policy["rules"][0]["type"], "pull_request")
        review = policy["rules"][0]["parameters"]
        self.assertEqual(review["required_approving_review_count"], 1)
        self.assertTrue(review["dismiss_stale_reviews_on_push"])
        self.assertTrue(review["require_last_push_approval"])
        self.assertTrue(review["required_review_thread_resolution"])


if __name__ == "__main__":
    unittest.main()
