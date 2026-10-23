# Project working location

The primary local checkout is `C:\code_project\f1-sim`. Prefer it for development and automation. Other OneDrive/Codex copies are retained for recovery, not a second independently maintained source tree. An existing Codex conversation may still be attached to a different worktree; use explicit working directories and do not silently edit the old copy.

Read `docs/local-workspace.md` for consolidation provenance, backups and task configuration. Preserve unrelated work, secrets, local data, existing branches and named Git stashes. Do not delete anything without explicit approval.

## Validation and automation

- Use the existing `.venv\Scripts\python.exe`; do not install or rebuild packages just to run tests.
- Run `python -m pytest -q` from this checkout for regression checks.
- `python -m scripts.auto_forecast --env-file .env.automation --check-only` checks eligibility without posting to Discord.
- Scheduled automation uses ignored `.env.automation`; `.env` is a separate preserved manual configuration. Never expose or commit either file.
- Preserve frozen files and delivery receipts byte-for-byte. A changed checkout path is not permission to rewrite frozen provenance or resend reports.
- Experimental accuracy candidates remain disabled. Read `docs/accuracy-improvements.md` and promotion gates before proposing a live parameter change.
- A source/test success does not prove existing `dist` executables contain these changes. Rebuild and verify a package separately when requested.
