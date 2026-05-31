# Contributing

Thanks for helping improve Amazon Music RPC.

## Before Opening An Issue

Check the latest release first:

https://github.com/eripum9/Amazon-Music-Discord-RPC/releases/latest

For bugs, include:

- Amazon Music RPC version
- Windows version
- Install type: installer, source, or Android beta APK
- Amazon Music source: Microsoft Store, website installer, or Android test app
- Whether enhanced metadata is enabled
- Whether fallback metadata or notification enrichment is enabled
- Exact steps to reproduce
- What happened
- What you expected
- Diagnostics export or copied diagnostics text with secrets removed

Do not post Last.fm session keys, ListenBrainz tokens, Discord tokens, config files with secrets, or screenshots with private account details.

## Branches

- `master` is the Windows release branch and contains the current Android beta source.
- `beta/androidbuild` is available for Android experiments before they are merged.
- `fix/*` branches are for focused issue fixes.
- `beta/*` branches are for experimental work that should not affect stable Windows releases.
- Linux and macOS work should not start until the platform roadmap criteria are met.

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

## Android Beta Development

Android beta work lives in `Android/`. Use `beta/androidbuild` for risky Android experiments before merging them back to `master`.

Build from the repository root:

```powershell
$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'
$env:ANDROID_HOME="$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT=$env:ANDROID_HOME
gradle -p Android assembleDebug --no-daemon
```

## Pull Requests

Keep pull requests focused. A good pull request includes:

- The problem being fixed
- The behavior change
- Screenshots for UI changes
- Test output
- Any compatibility notes for enhanced metadata, fallback mode, or Android beta behavior

For Windows releases, follow [docs/release-checklist.md](docs/release-checklist.md).

For platform expansion, follow [docs/platform-roadmap.md](docs/platform-roadmap.md).
