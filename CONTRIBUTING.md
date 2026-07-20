# Contributing

Thanks for helping improve Amazon Music RPC.

## Before Opening An Issue

Check the latest release first:

https://github.com/eripum9/Amazon-Music-Discord-RPC/releases/latest

For bugs, include:

- Amazon Music RPC version
- Platform and OS version
- Install type: Windows installer, macOS beta DMG, or source
- Amazon Music app version and source: Microsoft Store/website on Windows or the official macOS app
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
- `beta/MacOS` contains the experimental prototype for Amazon's official macOS desktop app.
- Android support is discontinued and Linux remains out of scope.

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

Python 3.12.10 is the official CI and release baseline. A root `.venv` can be created with `uv venv --python 3.12.10 --seed .venv`; it is ignored by Git.

Run checks:

```powershell
python -m py_compile Windows\main.py Windows\desktop_runtime.py Windows\app_models.py Windows\runtime_state.py Windows\task_supervisor.py Windows\structured_logging.py Windows\window_controller.py Windows\rpc_controller.py Windows\command_controller.py Windows\amazon_devtools.py Windows\media_reader.py Windows\discord_rpc.py Windows\config.py Windows\updater.py Windows\status_summary.py Windows\qt_tray_ui.py Windows\rpc_state.py Windows\metadata_pipeline.py Windows\launcher_diagnostics.py Windows\security_trust.py Windows\self_tests.py Windows\release_smoke.py
python -m pytest Windows\tests
pyright Windows\app_models.py Windows\runtime_state.py Windows\task_supervisor.py Windows\window_controller.py Windows\rpc_controller.py Windows\command_controller.py
ruff check Windows --select E9,F63,F7,F82
python Windows\release_smoke.py --allow-missing-installer
git diff --check
```

Build:

```powershell
Windows\build.bat
```

## macOS Beta Development

The macOS prototype is developed on `beta/MacOS`; do not describe it as a stable or notarized release. Install and run it from the repository root:

```bash
git checkout beta/MacOS
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r MacOS/requirements.txt
python -m pip install -r MacOS/requirements-build.txt
python -m MacOS.main
```

Run checks:

```bash
python -m pytest MacOS/tests Shared/tests
python -m compileall -q MacOS Shared
git diff --check
```

Build the menu-bar app and drag-install DMG:

```bash
MacOS/scripts/build_app.sh
MacOS/scripts/create_dmg.sh
```

The outputs are under `MacOS/dist/`. Mount `Amazon-Music-RPC.dmg`, drag `Amazon Music RPC.app` onto the Applications shortcut in the DMG, eject it, and test the copy in `/Applications`. A build without `MACOS_CODESIGN_IDENTITY` is only ad-hoc signed for local development and is not notarized.

The DevTools integration is primary. If the official Amazon Music app is already open normally, enabling it requires an explicit one-time restart; never add a silent process restart. The Now Playing reader is the read-only fallback. Changes to either path must preserve the validation and permission boundaries in [docs/macos-beta.md](docs/macos-beta.md), [docs/macos-integration-research.md](docs/macos-integration-research.md), and [MacOS/PERMISSIONS.md](MacOS/PERMISSIONS.md).

Discord was not installed during the first prototype build. Automated RPC mocks are useful regression coverage, but a pull request must identify live Discord, Last.fm, ListenBrainz, menu-bar, and clean-machine checks that were not actually performed.

## Pull Requests

Keep pull requests focused. A good pull request includes:

- The problem being fixed
- The behavior change
- Screenshots for UI changes
- Test output
- Any compatibility notes for enhanced metadata or fallback mode

For Windows releases, follow [docs/release-checklist.md](docs/release-checklist.md).

For supported platform scope, follow [docs/platform-roadmap.md](docs/platform-roadmap.md).

Architecture changes must preserve the controller boundaries in [docs/architecture.md](docs/architecture.md), and security-sensitive changes must update [docs/threat-model.md](docs/threat-model.md) or [docs/network-endpoints.md](docs/network-endpoints.md) when their trust boundaries change.

Platform-neutral playback behavior belongs in `Shared/`. Privacy rules, track normalization/corrections, custom-art matching, process-name matching, and scrobble eligibility must not silently diverge between Windows and macOS. A fundamental behavior change must update the shared implementation or both platform paths, with tests for both builds.
