# Desktop redesign and PC forecast updates

Weekly Fantasy prices, actual scores and schedule-based chronological session controls are described in [Fantasy data archive](fantasy-data-archive.md).

The desktop workbench uses the supplied F1 Simulator Desktop App design: Nocturne colours, racing-red accents, grouped Data / Setup / Analyse navigation, a workflow bar, setup cards, session buttons and a persistent run action. Existing archive, training, analysis and Simulation Centre controls use the real Python services. Prototype sample results and simulated progress are not imported.

**Follow PC runs** is enabled initially. On opening, and every 15 seconds while open, the app discovers completed forecast jobs in its own workspace and the PC automation workspace. The default PC location is `C:\code_project\f1-sim`; Settings lets you connect another existing directory. This setting is stored locally in `config/app_settings.json`, separately from credentials.

The newest verified forecast supplies displayed results and the default season, Grand Prix and cutoff session. Selection uses the frozen forecast's timezone-aware creation timestamp, rather than folder modification time. Every frozen manifest and its recorded checksums are verified. Running, failed, non-forecast and invalid bundles cannot become the latest forecast. No scheduler process, upload, training or new simulation is started by following.

Editing setup or starting a manual run pauses following. Enable the switch to return to the latest PC forecast. **Refresh now** refreshes the followed results; it does not discard manual setup while paused. Reset restores model/output defaults with the latest verified forecast's race selection. Saved-result labels continue to describe the actual displayed run.

Forecast probabilities and fantasy summaries use the frozen summary; supporting session, telemetry, strategy and chart exports are read from that forecast's `source` folder. Missing supporting exports remain unavailable. External PC forecasts also appear in Compare. Frozen forecast files and Discord delivery receipts are never copied over or rewritten by synchronization.

While following, the managed desktop FIA index also merges updates from the PC workspace, including when no new forecast completes. Previous CSV versions are backed up; custom data paths and custom columns are preserved. The FIA preview defaults to publication date descending across the entire dataset, with publication date displayed first. See [FIA document synchronization](fia-document-sync.md) for collection cadence and safeguards.

The design's calibrated confidence, official tyre allocations and editable model weights remain subject to the existing functionality audit. These are not fabricated from prototype values. New trained candidates remain inactive.

The app refreshes while open and reconnects at its next launch. The PC scheduled task must still run successfully to produce new forecasts. Following shows the latest saved forecast; its timestamp does not claim that upstream data is current.
