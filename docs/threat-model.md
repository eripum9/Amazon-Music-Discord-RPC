# Threat Model

## Scope

This model covers the Windows app, its installer and updater, Amazon Music enhanced metadata, the local Amazify bridge, local settings and logs, optional scrobblers, and official release artifacts.

## Protected Assets

- Last.fm session keys and ListenBrainz tokens
- Discord presence integrity and current playback metadata
- The installed executable and updater trust decision
- Local config, logs, and diagnostics exports
- The user’s Amazon Music session exposed through local DevTools

## Trust Boundaries

### GitHub Release Boundary

The updater accepts metadata and artifacts only from the configured GitHub repository and approved GitHub asset hosts. Redirects, names, sizes, and the detached SHA256 asset are validated before execution. Official artifacts originate from the manually triggered draft-release workflow on the current `master` commit.

### Amazon Music DevTools Boundary

Enhanced metadata opens a random reserved loopback port. The app validates the Amazon page URL, exact target identifier, selected port, WebSocket scheme, and listener ownership before reading DOM metadata. Failure returns to local fallback sources instead of attaching to an unrelated listener.

### Amazify Localhost Bridge

The Amazify localhost bridge exposes only RPC status and accepted commands required by the integration. A per-user random token is required on every request, comparisons are constant-time, request bodies are bounded, and browser access is allowed only from exact supported Amazon Music origins.

### Secret Storage Boundary

User tokens are stored in Windows Credential Manager and removed from normal config only after a verified round trip. DPAPI-protected local storage is a compatibility fallback. Logs, diagnostics, and normal exports redact or omit known secrets.

### Optional Service Boundary

Discord, Last.fm, ListenBrainz, Deezer, iTunes, GitHub, and remote artwork hosts receive only the data required for enabled features. Network controls and a redacted request history make optional traffic visible and independently controllable where practical.

## Primary Threats And Controls

| Threat | Control |
| --- | --- |
| Malicious release redirect or substituted installer | Exact repository/host validation, bounded downloads, mandatory detached SHA256, unique temp path, build attestation |
| Dependency compromise | Hash-locked release environment, Dependabot, pip-audit, CodeQL, dependency review |
| Attaching to an unrelated local DevTools service | Random reserved port, strict target URL and ID, listener ownership checks |
| Local website calling the Amazify bridge | Random bearer token, exact origin allowlist, bounded request body |
| Token exposure in config, logs, or reports | Credential Manager migration, DPAPI fallback, redaction audit, clear-token action |
| Stale or conflicting runtime state | Locked snapshots, typed models, controller ownership, supervised task shutdown |
| Silent optional network traffic | Per-provider controls, documented endpoints, redacted Diagnostics history |

## Residual Risks

- A process running as the same Windows user may read app memory or use that user’s Credential Manager entries.
- Enhanced metadata intentionally enables a local debugging interface while Amazon Music is running.
- Unsigned installers can trigger SmartScreen and do not provide publisher identity; users must verify the release checksum and GitHub provenance attestation.
- Third-party metadata layouts and APIs can change without notice and may reduce metadata quality.
- Discord ultimately controls whether Rich Presence buttons and assets are displayed.

Report sensitive findings through GitHub private vulnerability reporting as described in `SECURITY.md`.
