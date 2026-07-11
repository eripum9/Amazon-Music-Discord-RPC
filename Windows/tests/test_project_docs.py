from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_contribution_and_issue_templates_exist():
    required = [
        "CONTRIBUTING.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/ISSUE_TEMPLATE/enhanced_metadata.yml",
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
    assert "Android support has been discontinued" in readme
    assert "docs/platform-roadmap.md" in readme
    assert "CONTRIBUTING.md" in readme


def test_platform_roadmap_keeps_linux_and_macos_out_of_scope():
    roadmap = (ROOT / "docs/platform-roadmap.md").read_text(encoding="utf-8")
    assert "Windows is the sole supported target" in roadmap
    assert "Android support is discontinued" in roadmap
    assert "Linux and macOS are out of scope" in roadmap
    assert "official desktop apps" in roadmap
    assert "research/linux-metadata-rpc" not in roadmap
    assert "research/macos-metadata-rpc" not in roadmap


def test_official_release_workflow_keeps_trust_guards():
    workflow = (ROOT / ".github/workflows/release-draft.yml").read_text(encoding="utf-8")
    spec = (ROOT / "Windows/AmazonMusicRPC.spec").read_text(encoding="utf-8")
    lock = (ROOT / "Windows/requirements-release.lock").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "refs/heads/master" in workflow
    assert "--require-hashes" in workflow
    assert "origin/master" in workflow
    assert "--draft" in workflow
    assert "gh release create" in workflow
    assert "gh release publish" not in workflow
    assert "AmazonMusicRPC_Setup.exe.sha256" in workflow
    assert "attest-build-provenance@0f67c3f4856b2e3261c31976d6725780e5e4c373" in workflow
    assert "upx=False" in spec
    assert "strip=False" in spec
    assert "cryptography==48.0.1" in lock
    assert "--hash=sha256:" in lock
