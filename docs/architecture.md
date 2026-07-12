# Architecture

Amazon Music RPC v5 keeps the executable entry point small and separates application state, owned work, windows, commands, and Discord lifecycle from the playback pipeline.

## Runtime Boundaries

`Windows/main.py` starts `desktop_runtime.main()`. The desktop runtime composes these boundaries:

- `ApplicationState` owns synchronized config, current-track, RPC, and diagnostics snapshots.
- `TrackSnapshot` and `DiagnosticsSnapshot` are immutable typed values passed between runtime boundaries.
- `TaskSupervisor` names background tasks, captures failures, coordinates stop requests, and joins owned threads during shutdown.
- `RpcController` owns the Discord RPC lifecycle.
- `WindowController` owns Settings and Diagnostics subprocesses and monitors auto-saved config changes.
- `CommandController` maps tray and integration commands to explicit handlers.
- `StructuredLogTee` preserves the readable rotating console log and emits a redacted JSONL event stream.

The playback pipeline remains in `desktop_runtime.py` because source precedence, timing correction, scrobbling eligibility, privacy, artwork, and Discord updates form one stateful loop. New UI or transport behavior should enter through a controller instead of adding an independent global thread.

## Metadata Precedence

1. Amazify integration, when installed and actively connected.
2. Enhanced Amazon metadata through a validated local DevTools target.
3. Windows SMTC.
4. Optional Amazon Music notification enrichment.
5. Optional Deezer and iTunes lookup for missing artwork, album, duration, or selected links.

Each lower source is a fallback. It must not overwrite a complete higher-priority snapshot with older metadata.

## Process Model

The tray and playback loop live in the main process. Settings and Diagnostics are separate WebView2 subprocesses so a UI failure does not terminate playback. The updater reuses the frozen executable in a dedicated helper mode after the main process exits. Amazify communication uses a token-authenticated loopback bridge.

## Shutdown

Shutdown first stops accepting commands, requests supervised task cancellation, closes child windows and local bridges, disconnects Discord, joins owned non-daemon workers, and then releases the single-instance mutex. A new background task must either be owned by `TaskSupervisor` or expose an explicit stop-and-join lifecycle.

## Change Rules

- Keep data crossing controller boundaries typed and bounded.
- Keep config writes atomic and auto-saved through the existing config API.
- Do not log tokens, raw lookup queries, or unredacted config payloads.
- Add network destinations to `network-endpoints.md` and expose a user control when traffic is optional.
- Update `threat-model.md` when a trust boundary, local listener, updater path, or secret store changes.
