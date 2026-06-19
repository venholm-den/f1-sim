# Setup

## Requirements

- Windows PowerShell for the documented commands.
- Python matching the project virtual environment.
- Internet access for first FastF1/Open-Meteo data pulls.

## Create a Virtual Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## Install Runtime Dependencies

```powershell
pip install -r requirements.txt
```

## Install Development Dependencies

```powershell
pip install -r requirements-dev.txt
```

## Local Configuration

The default config lives at:

```text
config\default_run_config.json
```

The main editable local data files are:

```text
data\fantasy_prices.csv
data\track_profiles.csv
data\team_power_units.csv
data\fia_documents\fia_document_index.csv
```

Discord posting is optional and uses `.env`:

```text
POST_TO_DISCORD=true
DISCORD_WEBHOOK_URL=...
```

Keep `.env` local. It is ignored by Git.

## FastF1 Cache

FastF1 cache data is written under `data/cache/` when available. Cache folders are ignored by Git.

## Historical Model Artifacts

Historical training outputs are local generated artifacts:

```text
data\historical_model\
data\models\
```

Build them with:

```powershell
python scripts/build_historical_dataset.py --start-year 2022 --end-year 2026 --sessions Q R
python scripts/train_historical_model.py --historical-dir data\historical_model --model-dir data\models
```

If FastF1 rate limits the historical build, rerun later. Existing files are merge-safe and the builder skips already completed rows by default.
