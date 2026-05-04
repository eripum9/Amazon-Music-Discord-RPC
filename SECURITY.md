# Security Policy

## Supported versions

Only the latest release is actively maintained.

| Version | Supported |
|---|---|
| Latest | ✅ |
| Older releases | ❌ |

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, report them privately via [GitHub's private vulnerability reporting](https://github.com/eripum9/Amazon-Music-Discord-RPC/security/advisories/new).

Include:
- A description of the vulnerability and its potential impact.
- Steps to reproduce or a proof-of-concept if possible.
- Your suggested fix (optional but appreciated).

You can expect an initial response within a few days.

## Credential storage

Last.fm session keys and ListenBrainz tokens are stored in plain-text in `%APPDATA%\AmazonMusicRPC\config.json`. This file is readable only by the current Windows user account. Users who require stronger isolation should consider not storing credentials locally and re-entering them each session, or using file-system permissions to restrict access to the config directory.
