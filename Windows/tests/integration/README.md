<!-- MIT License - Copyright (c) 2026 eripum9 -->

# Runtime Integration Gate

Run from the repository root:

```powershell
python -m pytest Windows/tests/integration -q
```

These tests execute `desktop_runtime.rpc_loop`, its metadata pipeline, timing
state, resolved-choice store, and scrobble eligibility. Discord publishing and
scrobblers are recording fakes; Discord shutdown still uses the real adapter's
clear/close logic. Metadata, config, credentials, diagnostics, process launches,
and external network access are isolated. Only the HTTP deadline test permits
loopback traffic, using a stdlib server without external services.

When `ArtworkResolver` exists, its runtime request/result boundary is replaced
with a deterministic scheduler. Results are retained for the requested key;
duplicate requests do not restart a lookup. Completion can be delayed until
after a manual picker choice or track change. Tests do not inspect the real
resolver's implementation fields or run its worker thread.

The synchronous baseline runs all playback cases. The worker-close test,
streaming HTTP test, and scored-matcher test skip when their features are absent. The gate
checks paused Deezer results, a missing-duration 200s backfill scrobbling at
100s, manual correction precedence, skip identity, initial privacy, presence
pause/resume and seek timers, shutdown, and distinct-duration matcher candidates.
The known baseline wall-clock pause
scrobbling bug is deliberately outside this gate.

This is not a live Amazon Music/Discord test, a resolver concurrency stress
test, or the full unit suite. The loopback deadline check uses real time with
scheduling tolerance; playback tests use fake time and no sleeps.
