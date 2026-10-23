# Main local checkout

Use **`C:\code_project\f1-sim`** for future development and scheduled source runs. Consolidation on 3 October 2026 brought the newer Git baseline and local changes from the OneDrive checkout and Codex worktree into this folder.

The consolidation branch is `codex/consolidated-f1-sim`. Local code changes remain uncommitted; no GitHub push has been made. The old `webview-app-rebuild` branch is retained. Its modified strategy preview image was preserved in a named Git stash and a file backup; its content exactly matches the newer committed image.

The previous OneDrive checkout and Codex worktree are retained, not deleted. They are no longer the intended source-run location. This existing Codex conversation remains attached to its original worktree: open the main checkout explicitly for future tasks.

Source snapshots, complete Git history bundles and the previous task definition are backed up at `F:\Codex-Workspace-Backups\f1-sim-consolidation-20261003T071205`. Ignored source caches, outputs and credentials remain recoverable in their original folders; any runtime collisions overwritten during consolidation are separately backed up before replacement.

## Automation and Discord

The existing Windows task `F1 Sim - Session Forecast` uses the main checkout's Python interpreter and working directory. It retains its hourly schedule, 10,000 simulations and Discord upload setting.

The two original checkouts had different Discord webhook configurations. The main checkout's existing `.env` is preserved. Scheduled automation explicitly selects the ignored **`.env.automation`**, copied from the previously working automation checkout, so consolidation does not change its Discord destination. Do not commit either environment file or include its contents in reports.

Frozen forecast folders and delivery receipts are retained byte-for-byte under `outputs/app_runs`. Existing successful or uncertain delivery receipts prevent blind reposting. Frozen manifests/configs retain historical source paths for provenance and must not be rewritten merely to reflect the new checkout.

Read-only eligibility check:

```powershell
cd C:\code_project\f1-sim
.\.venv\Scripts\python.exe -m scripts.auto_forecast --env-file .env.automation --check-only
```

The check does not send Discord messages. Use the existing test environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Existing packaged executables in `dist` have not been rebuilt by consolidation. Source validation does not prove those older binaries include new features. Use source launchers until a new package has been built and tested.
