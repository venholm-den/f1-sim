# Automated forecasts on Windows

The automation checks the published F1 timetable once per hour. It creates a
local forecast only when the upcoming race has a newly eligible input state:
PRE, FP1, FP2, FP3, SQ, S or Q. Session status and usable lap/driver data are checked
first: a finalised/ended session can be selected without the three-hour delay.
Known live, interrupted or data-empty sessions are excluded. When readiness is
unavailable, the conservative scheduled-start-plus-three-hours fallback is used,
so the runner does not assume data is available immediately at session end.

Each race/session combination is run once after a valid frozen snapshot exists.
A failed download remains visible in Simulation Centre and is retried at the
next scheduled check. The runner holds the same workspace lock as Simulation
Centre, so it skips safely when the app is open and cannot overlap another run.

The automated mode uses 100,000 simulations, seed 42 and overtaking difficulty
0.55 by default. Discord and automated post-race scoring are opt-in.

The default increased on 25 October 2026. Existing unversioned 10,000-simulation
forecasts retain their official classification and frozen files. New official
jobs require 100,000 simulations; other counts remain available for personal runs.
The existing Windows task's explicit count was also updated, preserving its
schedule, environment file and upload/scoring options.

For source/config isolation and drift checks before scheduled execution, use
the [protected runtime workflow](protected-forecast-runtime.md). Development
merges must not silently replace the runtime used to collect a frozen cohort.

## Post-race analysis

Add `--post-race` to the scheduled runner to evaluate the latest completed,
prospective automated forecast for each race. With `--discord`, it also uploads
the analysis, forecast-versus-actual chart, classification and comparison tables.
Scoring opens eight hours after the scheduled race start and requires finished
session status, official results and complete driver coverage. Missing results
are recorded as failed jobs and retried on the next check. Each race has one
completed analysis; pending uploads retry even after the next race is eligible.
Successful or uncertain deliveries are never blindly reposted.
For a new task, the installer supports `-EnablePostRace -EnableDiscord`.

Prepare missing analyses locally without sending anything:

```powershell
.\.venv\Scripts\python.exe -m scripts.auto_forecast --env-file .env.automation --post-race-only
```

Add `--discord` to explicitly upload those reports. Post-race artifacts live in
separate score jobs under `outputs/app_runs`; frozen forecasts and their existing
delivery receipts are preserved. Single-race scores do not prove calibration.

## Preview the next action

This reads the current calendar and reports whether the eligible session is new:

```powershell
.\.venv\Scripts\python.exe -m scripts.auto_forecast --check-only
```

## Install the scheduled task

From PowerShell in the repository:

```powershell
.\scripts\install_forecast_task.ps1
```

The task starts its first check after approximately five minutes and repeats
hourly for the current signed-in Windows user. The computer must be awake and
the user logged on. `StartWhenAvailable` allows a missed check to run later.

Custom polling and simulation counts are supported:

```powershell
.\scripts\install_forecast_task.ps1 -IntervalMinutes 30 -SimulationCount 20000
```

The installer refuses to replace a task with the same name. Inspect it with:

```powershell
Get-ScheduledTask -TaskName "F1 Sim - Session Forecast"
```

To remove it later, explicitly run:

```powershell
Unregister-ScheduledTask -TaskName "F1 Sim - Session Forecast" -Confirm
```

Forecast history and logs remain under `outputs\app_runs`; removing the task
does not delete any forecasts.

## Discord uploads

Store the webhook locally in the ignored project `.env` file:

```text
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Then install the task with `-EnableDiscord`. A Discord upload happens only after
the forecast snapshot is frozen successfully. New compact delivery plans use
the dark 1600 × 1280 race-intelligence cards: race outlook, a points battle when
top-10 probabilities are available, and a forecast-update card when a verified
earlier forecast has matching drivers and probabilities. Cards lead the attachment
list, followed by the frozen simulation CSV and available Markdown/CSV driver evidence.
The embed shows changes against the latest earlier forecast for the same race,
modelled retirement risk, the data cutoff and assumptions. Roster changes block
like-for-like deltas. Missing probabilities are labelled rather than shown as zero.
FIA grid revisions compare against the exact superseded forecast, including
same-session Q revisions, rather than skipping back to the sprint. If that
explicit predecessor cannot be verified, the comparison is withheld.

New reports also explain the five leading drivers: projected pace rank, historical
and current-session evidence, effective pace input weights, grid source and
retirement risk. A Markdown explanation and CSV audit table accompany the compact
bundle when verified pace features are available. The dense all-driver evidence
chart remains a local supporting output and is attached in full-detail mode.
The explanation flags limited history, sparse laps, missing inputs and capped
pace. Input weights combine both blending stages; field normalisation also affects
pace ranks. They are not percentage-point contributions to win probability.

New forecasts freeze `baseline_race_features.csv` with the other hashed inputs,
so explanations can name each historical race, its pace rank, usable laps and
recency weight. Older snapshots retain their original manifests; unfrozen source
files are never used to fill missing provenance. Missing evidence is explicit.
Derived long-run scores are distinguished from experimental matched practice runs;
fuel-corrected performance is not claimed. Race weather and delayed-start scenarios
remain informational and do not affect live win probabilities. No forecasting
parameters or accuracy-candidate switches are changed by these report additions.

These source changes apply to new delivery plans. Saved plans and retry bundles
retain their exact original content. Older packaged apps require a rebuild to
generate these reports or read the added historical-evidence snapshot file.

Set `DISCORD_REPORT_DETAIL=full` in the selected local environment file to include
all available original report images, including fantasy value when prices are
available. Bundles larger than ten attachments use multiple messages, with
separate receipts so successful batches are not resent. A local receipt prevents duplicate posts;
failed posts are retried by the next scheduled check.

The message and attachment order are saved before the first upload. Retries keep
the same bundle even if the detail setting changes. Legacy partial batches keep
their original order. Successful historical receipts are never reformatted or
reposted. Requests use Discord's server-confirmed response and disable mentions.

Post-race embeds compare the model's finish error against the complete frozen
grid-position baseline on the same drivers. This is the grid captured in the
forecast, which may differ from the eventual race grid after later penalties.
Missing, duplicated or invalid grid positions withhold the baseline. Retirement
status and predicted DNF probability accompany the largest misses. The finish
error for drivers who did not retire is a diagnostic subset, not a pace accuracy
claim. The last five verified evaluated races provide a descriptive baseline
comparison when enough scores exist; one race does not establish calibration.
New post-race messages attach the dark scorecard and two results CSVs. The scorecard
shows finish error against the frozen-grid baseline and observed coverage of saved
middle-50% finish ranges, using only rows with valid range endpoints. Missing baselines
or ranges remain unavailable. Detailed JSON, text and the full-field comparison chart
remain available locally. A saved post-race delivery plan pins the payload and files;
existing completed reports, receipts and retries keep their original format.

### Day-before weekend briefing

Pass `--weekend-briefing` alongside `--discord` to enable a separate schedule/track
post. New task installations can use `-EnableWeekendBriefing`. The briefing is checked
independently of forecast eligibility, so an already completed PRE forecast does not
suppress it. `--post-race-only` does not trigger weekend briefings.

The first hourly check at or after **09:00 Europe/London on the calendar day before
FP1** can post it. Later checks on that same day can catch up if the PC was offline.
It never sends or retries after that UK day has ended. This uses the actual first
F1 session date, rather than assuming every weekend begins on Friday. GMT/BST is
converted for each session separately, including weekends crossing a clock change.

The graphic includes all five session starts in UK time, standard/sprint format,
resolved circuit, country, reference race laps and available reference lap length.
The accompanying embed uses Discord-local timestamps and links to the available
circuit reference. Circuit geometry is matched by circuit ID; unresolved/conflicting
venues withhold track figures. Reference values are labelled, not claimed as final
race bulletins. Missing UTC session starts or a testing event cannot create a post.

Exactly one saved briefing per `(year, round)` lives under
`outputs/weekend_briefings`. Its message, graphic, source schedule and checksums are
pinned before delivery. Successful receipts prevent duplicates; ordinary HTTP failures
back off within the same day. Interrupted/uncertain uploads require review and are
never automatically resent. A calendar/briefing failure is visible in automation health
without preventing the forecast workflow from continuing.

Read-only eligibility check (does not post or prepare a briefing):

```powershell
.\.venv\Scripts\python.exe -m scripts.auto_forecast --env-file .env.automation --weekend-briefing --check-only
```

Preview existing runs without modifying them or sending messages:

```powershell
.\.venv\Scripts\python.exe -m scripts.preview_discord_reports --forecast-id <forecast-job-id> --score-id <score-job-id>
```

This creates a local HTML preview, embed JSON and charts in a new directory under
`outputs/discord_output_previews`. It does not load credentials or call Discord.

Pending uploads are checked across all completed automated runs, even after
the next session or race becomes eligible. HTTP failures use an increasing
retry delay (15 minutes up to six hours). A transport error or interrupted
upload is marked uncertain for review because Discord may have accepted it;
it is not automatically posted again. Delivery state is saved in each run's
`discord_post_result.json`.

Charts and frozen tables now use one pipeline simulation, including its session
weather modifiers and fantasy metrics. Target-session classifications define
the driver roster; historical substitutes are excluded. A missing model driver
or duplicate identifier stops the run. Before FP1, the latest baseline race's
roster is used as an explicit assumption. Each new frozen snapshot includes
`driver_roster.csv` for provenance. Existing snapshots are preserved.

Do not commit `.env` or paste the webhook into task arguments, logs or source.
