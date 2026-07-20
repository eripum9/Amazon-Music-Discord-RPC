# Threat Model

## Scope

This model covers the stable Windows app and its installer/updater, the macOS
beta app and its DMG updater, Amazon Music enhanced metadata on both platforms,
the local Amazify bridge, local single-instance channels, settings and logs,
optional scrobblers, and release artifacts.

## Protected Assets

- Last.fm session keys and ListenBrainz tokens in Windows Credential Manager,
  the DPAPI fallback, or macOS Keychain
- Discord presence integrity and current playback metadata
- The installed executable and updater trust decision
- Local config, logs, and diagnostics exports
- The user’s Amazon Music session exposed through local DevTools
- The owner-only macOS single-instance socket and commands accepted through it

## Trust Boundaries

### GitHub Release Boundary

The updaters accept metadata and artifacts only from the configured GitHub
repository and approved GitHub asset hosts. Redirects, names, and sizes are
validated. The Windows updater verifies the installer before handing it to the
operating system. The macOS beta downloads only the exact DMG asset after a
matching SHA256 has been obtained, verifies the final bytes, and opens the DMG
for an explicit drag install; it does not replace the installed app silently.
Official Windows artifacts originate from the manually triggered draft-release
workflow on the current `master` commit. The local macOS beta build remains an
ad-hoc-signed prototype unless a release operator explicitly performs the
documented Developer ID and notarization workflow.

### Amazon Music DevTools Boundary

Enhanced metadata opens a random reserved loopback port. Both implementations
validate the Amazon page URL, exact target identifier, selected port, WebSocket
scheme, and listener ownership before reading DOM metadata. Failure returns to
local fallback sources instead of attaching to an unrelated listener.

On macOS, the integration accepts only `/Applications/Amazon Music.app` with
the expected bundle identifier, executable name, Amazon Team ID, and signing
authority. A listener is trusted only when its process executable resolves to
an allowlisted executable inside that installation, its endpoint is loopback
and in the private high-port range, and a validated Amazon page target matches.
Listener ownership is checked before target discovery and again around the
bounded read-only evaluation. A fresh RPC process may rediscover an existing
listener only when socket ownership metadata yields one trusted candidate, but
it does not inspect Amazon's command line, browser profile, cookies, storage, or
account files.

Restarting an already-running normal Amazon Music session is an explicit user
action. Disabling attachment does not by itself remove a listener already owned
by Amazon Music; the user must explicitly relaunch Amazon Music normally (or
close it) to remove that endpoint.

### Amazify Localhost Bridge

The Amazify localhost bridge exposes only RPC status and accepted commands required by the integration. A per-user random token is required on every request, comparisons are constant-time, request bodies are bounded, and browser access is allowed only from exact supported Amazon Music origins.

### Secret Storage Boundary

On Windows, user tokens are stored in Credential Manager and removed from
normal config only after a verified round trip; DPAPI-protected local storage is
a compatibility fallback. On macOS, scrobbler secrets are generic-password
items in the user's login Keychain and are omitted from `config.json`.
Diagnostics and normal exports redact or omit known secrets on both platforms.

### macOS Single-Instance Boundary

The macOS beta uses a file lock plus a Unix-domain command socket. Its app-data
directory is made owner-only, the socket is mode `0600`, stale socket removal
requires a socket owned by the current UID, and commands are limited to a small
allowlist such as opening Settings or Diagnostics and quitting. It does not
accept arbitrary paths, shell commands, or network clients.

### Optional Service Boundary

Discord, Last.fm, ListenBrainz, Deezer, iTunes, GitHub, and remote artwork hosts receive only the data required for enabled features. Network controls and a redacted request history make optional traffic visible and independently controllable where practical.

## Primary Threats And Controls

| Threat | Control |
| --- | --- |
| Malicious release redirect or substituted installer/DMG | Exact repository/host validation, bounded downloads, mandatory checksum for automatic handoff, unique temp path; Windows release attestation |
| Dependency compromise | Hash-locked release environment, Dependabot, pip-audit, CodeQL, dependency review |
| Attaching to an unrelated local DevTools service | Random reserved port, strict target URL and ID, listener ownership checks; on macOS, official bundle identity and executable-path checks plus fail-closed rediscovery |
| Local website calling the Amazify bridge | Random bearer token, exact origin allowlist, bounded request body |
| Token exposure in config, logs, or reports | Credential Manager/DPAPI on Windows, Keychain on macOS, secret omission and redaction |
| Untrusted local process sending macOS instance commands | Owner-only directory and socket, UID/type checks, command allowlist |
| Stale or conflicting runtime state | Locked snapshots, typed models, controller ownership, supervised task shutdown |
| Silent optional network traffic | Per-provider controls, documented endpoints, redacted Diagnostics history |

## Residual Risks

- A process running as the same desktop user may read app memory or invoke that
  user's credential facilities. Operating-system secret storage is not a
  defense against already-compromised same-user code.
- Enhanced metadata intentionally enables a local debugging interface while
  Amazon Music is running. The CEF endpoint has no Amazon Music RPC
  authentication; another process running as the same local user may discover
  and connect to it even though remote-network access is blocked by loopback.
  Closing Amazon Music or explicitly relaunching it normally removes the
  endpoint.
- Unsigned installers can trigger SmartScreen and do not provide publisher identity; users must verify the release checksum and GitHub provenance attestation.
- Ad-hoc-signed macOS beta DMGs are not notarized public releases and can be
  blocked by Gatekeeper after download. A public build requires Developer ID
  signing, notarization, and clean-machine verification.
- Third-party metadata layouts and APIs can change without notice and may reduce metadata quality.
- Discord ultimately controls whether Rich Presence buttons and assets are displayed.

Report sensitive findings through GitHub private vulnerability reporting as described in `SECURITY.md`.
