# Architecture

Amazon Music RPC v5 keeps platform entry points small and separates native metadata, startup, and packaging from platform-neutral playback decisions. Windows remains the published stable platform; the macOS implementation is an active beta maintained alongside it on `master`.

## Windows Runtime Boundaries

`Windows/main.py` starts `desktop_runtime.main()`. The desktop runtime composes these boundaries:

- `ApplicationState` owns synchronized config, current-track, RPC, and diagnostics snapshots.
- `TrackSnapshot` and `DiagnosticsSnapshot` are immutable typed values passed between runtime boundaries.
- `TaskSupervisor` names background tasks, captures failures, coordinates stop requests, and joins owned threads during shutdown.
- `RpcController` owns the Discord RPC lifecycle.
- `WindowController` owns Settings and Diagnostics subprocesses and monitors auto-saved config changes.
- `CommandController` maps tray and integration commands to explicit handlers.
- `StructuredLogTee` preserves the rotating console log and emits a redacted JSONL event stream.

The stateful Windows source/presence loop remains in `desktop_runtime.py`. New UI or transport behavior should enter through a controller instead of adding an independent global thread.

## macOS Beta Runtime Boundaries

`MacOS/main.py` starts the PySide menu-bar application and composes:

- `MacRuntime`, which owns metadata polling, Discord presence, artwork, privacy state, and scrobbler lifecycles.
- `RuntimeDependencies`, which keeps native readers and outbound services replaceable in tests.
- `MacOS/amazon_devtools.py`, which owns validated launch/restart, listener ownership, CDP target validation, and bounded metadata evaluation.
- `MacOS/media_reader.py` plus `amazon_music_now_playing.js`, which provide the read-only owner-validated Now Playing fallback.
- `MacOS/config.py`, which owns atomic config updates, Keychain-backed secrets, redaction, and the optional per-user LaunchAgent.
- `MacOS/ui.py`, which owns the menu-bar item, Settings, Diagnostics, file pickers, and update actions.
- `MacOS/single_instance.py`, which owns a per-user file lock and owner-only Unix command socket.
- `MacOS/updater.py`, which accepts only bounded GitHub release metadata and checksum-verified DMG assets.

The menu bar, runtime, Settings, and Diagnostics share one Qt application. Blocking metadata, network, and file work must remain outside the UI thread and have bounded timeout/shutdown paths.

## Shared Playback Behavior

`Shared/playback.py` is the pure-Python behavior layer consumed by Windows and macOS. It owns track normalization, privacy keyword matching, process-name/game-mode matching, remembered corrections, custom-art matching, and scrobble eligibility. The shared threshold is at least 30 seconds played plus either half of a known duration or 240 seconds.

Platform-native metadata and lifecycle code may differ, but user-visible rules must not drift. A fundamental behavior change must update the shared implementation or deliberately update both platform paths and their tests. A UI rewrite or runtime split that changes behavior must be carried across Windows and macOS unless the difference is intrinsically platform specific.

## Windows Metadata Precedence

1. Amazify integration, when installed and actively connected.
2. Enhanced Amazon metadata through a validated local DevTools target.
3. Windows SMTC.
4. Optional Amazon Music notification enrichment.
5. Optional Deezer and iTunes lookup for missing artwork, album, duration, or selected links.

Each lower source is a fallback. It must not overwrite a complete higher-priority snapshot with older metadata.

## macOS Metadata Precedence

1. Enhanced Amazon metadata through a validated local DevTools target.
2. Read-only macOS Now Playing data owned exactly by `com.amazon.music`.
3. Optional Deezer/iTunes lookup for missing public artwork or related metadata.

If Amazon Music is already running without a DevTools listener, the runtime reports that a restart is required. Restarting Amazon Music must remain an explicit user action; it is never an implicit metadata fallback. A lower source must not overwrite a complete current DevTools snapshot.

## Process Models

On Windows, the tray and playback loop live in the main process. Settings and Diagnostics are separate WebView2 subprocesses so a UI failure does not terminate playback. The updater reuses the frozen executable in a dedicated helper mode after the main process exits. Amazify communication uses a token-authenticated loopback bridge.

On macOS, the menu bar and playback runtime share one process. The beta runtime can start the validated Amazon Music executable with loopback metadata flags when Amazon Music is not running; replacing an already-running normal session requires an explicit enhanced-metadata restart. It invokes `/usr/bin/osascript` as a bounded fallback probe and never attaches to or injects into Amazon Music. A mode-`0600` Unix socket accepts only a small allowlist of same-user single-instance commands.

## Shutdown

Windows shutdown first stops accepting commands, requests supervised task cancellation, closes child windows and local bridges, disconnects Discord, joins owned non-daemon workers, and releases the single-instance mutex. A new background task must either be owned by `TaskSupervisor` or expose an explicit stop-and-join lifecycle.

macOS shutdown stops polling and outbound services, clears Discord presence, closes Qt UI state, removes the owned Unix command socket, and releases the file lock. Ordinary Amazon Music RPC shutdown does not terminate Amazon Music.

## Change Rules

- Keep data crossing controller/runtime boundaries typed and bounded.
- Keep config writes atomic and auto-saved through the platform config API.
- Do not log tokens, raw lookup queries, or unredacted config payloads.
- Add network destinations to `network-endpoints.md` and expose a user control when traffic is optional.
- Update `threat-model.md` when a trust boundary, local listener, updater path, or secret store changes.
- Preserve the explicit macOS restart boundary and exact Amazon bundle/listener/target validation.
- Keep platform-neutral playback rules in `Shared/` and cover fundamental changes on both platforms.
