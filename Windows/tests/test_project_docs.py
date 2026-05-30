from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_contribution_and_issue_templates_exist():
    required = [
        "CONTRIBUTING.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/ISSUE_TEMPLATE/enhanced_metadata.yml",
        ".github/ISSUE_TEMPLATE/android_beta.yml",
        "docs/android-beta.md",
    ]
    missing = [path for path in required if not (ROOT / path).exists()]
    assert missing == []


def test_bug_template_collects_required_support_data():
    template = (ROOT / ".github/ISSUE_TEMPLATE/bug_report.yml").read_text(encoding="utf-8")
    required_fields = [
        "app_version",
        "install_type",
        "windows_version",
        "amazon_music_source",
        "enhanced_metadata",
        "fallback_metadata",
        "steps",
        "diagnostics",
    ]
    assert all(field in template for field in required_fields)
    assert "Last.fm session keys" in template
    assert "Recent log lines" in template


def test_readme_keeps_landing_and_support_links():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Spotify-style Discord Rich Presence for Amazon Music on Windows" in readme
    assert "releases/latest" in readme
    assert "wiki/troubleshooting" in readme
    assert "wiki/privacy" in readme
    assert "docs/android-beta.md" in readme
    assert "CONTRIBUTING.md" in readme
