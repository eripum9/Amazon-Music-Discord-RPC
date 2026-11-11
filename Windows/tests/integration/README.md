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

Normally the `ArtworkResolver` runtime request/result boundary is replaced
with a deterministic scheduler. Results are retained for the requested key;
duplicate requests do not restart a lookup. Completion can be delayed until
after a manual picker choice or track change. Tests do not inspect the real
resolver's implementation fields or run its worker thread. The stop/private
restart test instead runs the real worker with an event-gated lookup: it
blocks A, queues B, closes the session, and proves B never starts and the
worker exits. `../test_artwork_resolver.py` separately tests generations,
cancellation, failures, and duplicate requests.

The original baseline tests retain feature-absence skips so they can be
compared with historical revisions. The follow-up tests require the new
resolver/matcher interfaces. The gate
checks paused Deezer results, a missing-duration 200s backfill scrobbling at
100s, manual correction precedence, skip identity, initial privacy, presence
pause/resume and seek timers, shutdown, and distinct-duration matcher candidates.
Additional cases cover same-identity manual corrections, custom precedence,
hidden-track cancellation, authoritative native durations, and new tracks
first observed paused.

This is not a live Amazon Music/Discord test, a resolver concurrency stress
test, or the full unit suite. Loopback tests use real time with scheduling
tolerance, including trickling headers and bodies, cancellation that frees
the worker, size/redirect rejection, and a real slow provider followed by a
successful fallback. Playback tests use fake time and no sleeps.

The lifecycle regressions also interleave stop/privacy with the first
resolver's construction and registration, and exercise quit with A running
and B queued. Related `../test_artwork_http.py` tests bound multi-address TCP,
TLS handshakes, and verified TLS bodies, including cancellation. Its public
test certificate/key is used only on loopback; no credentials are needed.
HTTP and HTTPS CONNECT proxies and both Requests CA-bundle environment
variables have positive controls.

OS DNS resolution remains synchronous and non-interruptible; cancellation
and the absolute deadline are checked immediately when it returns, before
opening a socket. No auxiliary DNS thread is created. SOCKS proxies are
explicitly rejected rather than silently falling back to a direct connection.
