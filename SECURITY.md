# Security Policy

## Supported Versions

This project is currently in pre-release. Security fixes are handled on the latest published pre-release and the default branch.

| Version | Supported |
| --- | --- |
| Latest pre-release | Yes |
| Default branch | Yes |
| Older releases | No |

## Reporting a Vulnerability

Please do not open a public issue for vulnerabilities, secrets, credential exposure, or private data exposure.

Use GitHub's private vulnerability reporting from the repository Security tab when available. Include:

- A short summary of the issue.
- Steps to reproduce or a proof of concept.
- Affected files, commands, or release versions.
- Any known workarounds.

If private vulnerability reporting is not available, open a minimal public issue asking for a private contact path without including exploit details.

## Secrets and Local Data

Do not commit `.env` files, Discord webhooks, API keys, FastF1 cache data, generated model artifacts, local outputs, or personal data exports. The repository intentionally ignores generated folders such as `outputs/`, `build/`, `dist/`, `data/cache/`, `data/historical_model/`, and `data/models/`.
