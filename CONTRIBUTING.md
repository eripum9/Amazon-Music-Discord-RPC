# Contributing

Thanks for helping improve Amazon Music RPC.

## Before Opening An Issue

Check the latest release first:

https://github.com/eripum9/Amazon-Music-Discord-RPC/releases/latest

For bugs, include:

- Amazon Music RPC version
- Windows version
- Install type: installer or source
- Amazon Music source: Microsoft Store or website installer
- Whether enhanced metadata is enabled
- Whether fallback metadata or notification enrichment is enabled
- Exact steps to reproduce
- What happened
- What you expected
- Diagnostics export or copied diagnostics text with secrets removed

Do not post Last.fm session keys, ListenBrainz tokens, Discord tokens, config files with secrets, or screenshots with private account details.

## Branches

- `master` is the Windows release branch.
- `fix/*` branches are for focused issue fixes.
- `beta/*` branches are for experimental work that should not affect stable Windows releases.
- Android support is discontinued. Linux and macOS are out of scope unless Amazon releases official desktop apps for those platforms.

## Windows Development

Install dependencies:

```powershell
pip install -r Windows\requirements.txt
pip install -r Windows\requirements-dev.txt
```

Run from source:

```powershell
python Windows\main.py
```

Run checks:

```powershell
python -m py_compile Windows\main.py Windows\amazon_devtools.py Windows\media_reader.py Windows\discord_rpc.py Windows\config.py Windows\updater.py Windows\status_summary.py Windows\qt_tray_ui.py Windows\rpc_state.py Windows\metadata_pipeline.py Windows\launcher_diagnostics.py Windows\security_trust.py Windows\self_tests.py Windows\release_smoke.py
python -m pytest Windows\tests
python Windows\release_smoke.py --allow-missing-installer
git diff --check
```

Build:

```powershell
Windows\build.bat
```

## Pull Requests

Keep pull requests focused. A good pull request includes:

- The problem being fixed
- The behavior change
- Screenshots for UI changes
- Test output
- Any compatibility notes for enhanced metadata or fallback mode

For Windows releases, follow [docs/release-checklist.md](docs/release-checklist.md).

For supported platform scope, follow [docs/platform-roadmap.md](docs/platform-roadmap.md).
