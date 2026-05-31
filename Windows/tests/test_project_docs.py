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
        "docs/platform-roadmap.md",
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
    assert "docs/platform-roadmap.md" in readme
    assert "CONTRIBUTING.md" in readme


def test_platform_roadmap_keeps_linux_and_macos_out_of_scope():
    roadmap = (ROOT / "docs/platform-roadmap.md").read_text(encoding="utf-8")
    android = (ROOT / "docs/android-beta.md").read_text(encoding="utf-8")
    assert "Linux and macOS are out of scope" in roadmap
    assert "official desktop apps" in roadmap
    assert "research/linux-metadata-rpc" not in roadmap
    assert "research/macos-metadata-rpc" not in roadmap
    assert "Repeatable Emulator Test Path" in android
    assert "Beta Exit Criteria" in android
