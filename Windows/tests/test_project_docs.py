# MIT License - Copyright (c) 2026 eripum9

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_contribution_and_issue_templates_exist():
    required = [
        "CONTRIBUTING.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/ISSUE_TEMPLATE/enhanced_metadata.yml",
        "docs/platform-roadmap.md",
        "docs/architecture.md",
        "docs/threat-model.md",
        "docs/network-endpoints.md",
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
    assert "Network controls" in readme
    assert "docs/architecture.md" in readme
    assert "docs/threat-model.md" in readme
    assert "docs/network-endpoints.md" in readme


def test_trust_documents_cover_v5_boundaries():
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    privacy = (ROOT / "docs/privacy.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs/architecture.md").read_text(encoding="utf-8")
    threat_model = (ROOT / "docs/threat-model.md").read_text(encoding="utf-8")
    endpoints = (ROOT / "docs/network-endpoints.md").read_text(encoding="utf-8")
    assert "private vulnerability reporting" in security
    assert "Windows Credential Manager" in privacy
    assert "TaskSupervisor" in architecture
    assert "Amazify localhost bridge" in threat_model
    destinations = {
        line.split("|")[1].strip().strip("`")
        for line in endpoints.splitlines()
        if line.startswith("| `")
    }
    assert {"api.deezer.com", "itunes.apple.com", "api.github.com"}.issubset(destinations)


def test_platform_roadmap_keeps_windows_stable_and_tracks_macos_beta():
    roadmap = (ROOT / "docs/platform-roadmap.md").read_text(encoding="utf-8")
    assert "Windows is stable; macOS is an experimental beta" in roadmap
    assert "| macOS | Beta prototype | `beta/MacOS` |" in roadmap
    assert "Fundamental user-visible behavior must be implemented and tested for both platforms" in roadmap
    assert "Android support is discontinued" in roadmap
    assert "Linux remains out of scope" in roadmap
    assert "official desktop app surface" in roadmap
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
    assert "cryptography==49.0.0" in lock
    assert "pillow==12.3.0" in lock
    assert "pillow==12.2.0" not in lock
    assert "pytest-cov==7.1.0" in lock
    assert "--hash=sha256:" in lock
    assert "WINDOWS_SIGNING" not in workflow
    assert "signtool" not in workflow.lower()
    assert "--expected-pillow 12.3.0" in workflow


def test_pytest_enforces_measurable_coverage_floor():
    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/windows-tests.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github/workflows/release-draft.yml").read_text(encoding="utf-8")
    assert "fail_under = 45" in config
    assert "--cov-fail-under=45" in workflow
    assert "--cov-fail-under=45" in release
    assert "Pytest with coverage threshold" in workflow


def test_windows_workflows_use_winsdk_wheel_runtime():
    release = (ROOT / ".github/workflows/release-draft.yml").read_text(encoding="utf-8")
    tests = (ROOT / ".github/workflows/windows-tests.yml").read_text(encoding="utf-8")
    security = (ROOT / ".github/workflows/security.yml").read_text(encoding="utf-8")
    for workflow in (release, tests, security):
        assert 'python-version: "3.12.10"' in workflow
    assert "--only-binary=winsdk" in release
    assert "--only-binary=winsdk" in tests


def test_windows_runtime_avoids_powershell_policy_bypass_and_packages_security_modules():
    runtime_sources = [
        (ROOT / "Windows/updater.py").read_text(encoding="utf-8"),
        (ROOT / "Windows/amazon_devtools.py").read_text(encoding="utf-8"),
        (ROOT / "Windows/windows_file_dialog.py").read_text(encoding="utf-8"),
    ]
    spec = (ROOT / "Windows/AmazonMusicRPC.spec").read_text(encoding="utf-8")
    assert all("ExecutionPolicy" not in source and "Bypass" not in source for source in runtime_sources)
    assert "'credential_store'" in spec
    assert "'network_audit'" in spec
