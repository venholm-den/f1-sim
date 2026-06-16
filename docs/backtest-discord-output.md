# Backtest Discord output

The backtest can now create Discord-friendly PNGs and optionally post them to a Discord webhook.

## Run without posting

```powershell
python -m src.backtest
```

This writes the normal CSV files plus PNG summaries to `outputs/backtest/`.

Important PNGs:

- `latest_prediction_snapshot_strategy_comparison.png`
- `latest_prediction_snapshot_metrics.png`
- `latest_prediction_snapshot_finish_comparison.png`

## Post to Discord

Set a webhook URL in your shell:

```powershell
$env:BACKTEST_DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

Then run:

```powershell
python -m src.backtest --post-discord
```

Or pass the URL directly:

```powershell
python -m src.backtest --post-discord --discord-webhook-url "https://discord.com/api/webhooks/..."
```

## Data source note

The tyre strategy comparison is reconstructed from FastF1 race lap/stint compound data. It is not FIA/Pirelli barcode-level tyre set allocation data.
