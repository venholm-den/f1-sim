# Historical Data page

Open **Historical Data** in the workbench sidebar. Select individual seasons or
a year range, choose the data coverage and click **Download selected seasons**.

- **Detailed sessions (2018 onwards):** practice, qualifying, sprint qualifying,
  sprint and race laps, sectors, tyres, results, observed weather and race-control
  data where published. Session types absent from a weekend are not requested.
- **Race classifications (1950 onwards):** published results through FastF1's
  Jolpica interface. These older results do not imply timing/weather availability.
- **Optional telemetry:** raw car and position samples, stored as compressed
  per-driver CSV files. Keep this off unless needed; several seasons can require
  substantial disk space. Telemetry is excluded from the combined analytics export
  but remains available in each session's saved version.

Provider documentation: [FastF1 Jolpica interface](https://github.com/theOehrly/Fast-F1/blob/main/docs/api_reference/jolpica.rst),
[Jolpica results endpoint](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/results.md).

## Resume and coverage

Downloads run in a separate process with live session counts and a log.
**Stop download** stops after the current session and retains completed data.
**Resume / retry this download** uses the original years, session types and
telemetry choice. Already committed files are checked against their hashes and
skipped. Missing/failed sessions are retried. A provider rate limit pauses the job;
wait before resuming. Starting the same selection later also resumes it.

Usable session tables are saved even when requested telemetry is unavailable.
These sessions are counted as saved with incomplete telemetry and remain marked
for retry. Their provenance records distinguish requested from available telemetry;
resuming with telemetry enabled creates a new version and retains the old files.
Resuming without telemetry skips the saved base data.

The downloader records HTTP error codes without storing request URLs or contents.
If the primary timing server refuses access with HTTP 401/403 and its mirror also
fails for the same files in two consecutive attempted sessions, the job pauses
early with the provider error. Restore access before resuming: a request-limit
countdown expiring does not resolve an access refusal. Successful mirror fallback
does not trigger this pause. Existing cached sessions remain usable.

Closing the app can interrupt a worker. The last fully committed session remains
usable; any incomplete version is retained but not counted as completed.
Downloading additional telemetry creates a new version, preserving the previous
one. The page offers no destructive cleanup action.

Calendars restrict collection to sessions scheduled before the current UTC day.
Detailed timing sessions must also report a terminal status and usable laps;
races need a complete classification. Future/current-day sessions and cancelled
events with unavailable data are not treated as completed downloads. Optional
missing weather/results/control tables are recorded in provenance.

Each session lives under:

```text
<workspace>/data/historical_library/<year>/<coverage>/<round_event_session>/
    session.json                # committed version and file hashes
    versions/<version>/
        *.csv.gz                # actual downloaded tables
        provenance.json
```

The library table counts saved sessions, laps/classifications and committed file
size. It does not equate cached requests with a complete season. Cache files and
older retained versions consume additional space; the displayed free-space figure
is the actual workspace-drive capacity.

## Use the data

**Race Setup → Track Overview** now reads your downloaded position telemetry
directly. Select the season/event/session; you do not need to run a simulation
first. The app selects a complete timed lap, rejects partial arcs and garage
coordinates, and shows the source session/driver beneath the map. If the selected
session has no usable telemetry, another downloaded session of the same race
may supply geometry. PRE remains available and can show this geometry without
feeding race observations into the PRE model. **Inspect downloaded telemetry**
opens the same archive map with saved lap/sector timings. Earlier seasons can supply
a labelled outline reference only when physical circuit and layout IDs match.
References supply no current lap/sector records, never use later seasons for an
earlier target, and cannot substitute conflicting or unknown identities.

**Model Training** in the sidebar trains separate candidate models directly from
selected detailed seasons with matched Q/R sessions. See [model-training.md](model-training.md)
for chronological validation, required coverage and saved outputs.

Click a library row to preview downloaded CSV records with pagination.
**Open library folder** opens the archive in Explorer.
**Export selected seasons to CSV** combines the saved seasons of the chosen
coverage type into a fresh `data/historical_library/exports/<timestamp_id>` folder.
Detailed exports use the existing `fastf1_laps.csv`, `fastf1_race_results.csv`,
weather, strategy and control filenames. Classification-only exports contain
`race_classifications.csv`. Both include an `export.json` record.

The archive can be expanded across all supported years without a per-job season
cap. Requests are sequential with pauses; completion depends on network, provider
limits, data availability and free disk space. Historical caches are reused.

Downloading/exporting does not automatically train or promote a model, rewrite
forecasts or send Discord messages. Historical observations are retrospective
inputs; any predictive accuracy claim still needs chronological validation.

## F1 account sign-in (October 2026 archive change)

F1 now requires authentication for timing archive downloads. An active F1 TV
Access subscription or higher is required; a free F1 account is insufficient.
Race classifications from Jolpica and already cached data remain usable.

In **Historical Data → F1 Account**, click **Sign in to F1**. The system browser
opens FastF1's supported sign-in helper. Install the FastF1 Companion browser
extension if prompted and complete the F1 sign-in there. Passwords are entered
only in the browser, never in the app or chat. The app verifies the signed token
and checks one historical file before saving it in FastF1's per-user token store,
outside the project and download logs. Sign-in expires; the panel shows the
expiry and allows signing in again. Login attempts time out after five minutes
and can be cancelled without removing an existing saved token.

After **Historical timing access verified**, resume the paused download. Saved
complete sessions are skipped, while missing telemetry can be retried. Workers
never launch an interactive login: sign in from the app before resuming if the
token has expired. This integration pins FastF1 **3.9.0a0**, the upstream alpha
that supports archive authentication. Existing executables need a new build.

Upstream: https://github.com/theOehrly/Fast-F1/issues/978

## API request meter

**Historical Data → Download progress → API request meter** shows live request
observations for newly started download workers:

- Network requests during the last rolling 60 minutes, across monitored
  historical download jobs in this workspace, including stopped/resumed jobs.
- Network attempts, HTTP cache hits and cached processed datasets for the
  selected job. Cache hits never increment network traffic. A processed
  dataset cache hit is a separate unit, not a claim about requests saved.
- Traffic by Formula 1 timing, Jolpica/Ergast, OpenF1, GitHub calendars and
  other HTTP providers, when observed.
- The selected worker's installed FastF1 guards, remaining slots and next
  expiry/available-slot estimate. FastF1's general 500/hour guard is shared
  across its providers; each provider does not get a separate 500 allowance.
- A server's `Retry-After` countdown when returned with HTTP 429. Unknown
  provider allowances/reset times stay unknown. The meter changes no limits
  and does not automatically resume a paused download.

The normal two-second UI poll also refreshes paused-job countdowns. Counts
observe actual HTTP transport attempts, including failures and redirects;
low-level retries hidden inside an HTTP adapter are not counted individually.
Other apps, forecasts, separate download scripts and older uninstrumented
workers are outside this meter, so it is not account-wide provider usage.

Restart the source app to load the updated panel, then start/resume a download.
An already running worker cannot acquire monitoring retrospectively. Old
downloads show an unavailable count instead of a misleading zero. Existing
packaged executables require a separate rebuild; source runs include it now.

Each new job retains `api_requests.jsonl` and `request_usage.json` in its
`outputs/app_runs/<job>` folder. The journal keeps timestamps, provider labels
and event types, without URLs, query parameters, credentials or response
bodies. The metadata snapshots FastF1's existing guard state. Reading the job
recomputes rolling usage and expiry at the current time. Completed archive
partitions and frozen forecasts remain unchanged.
