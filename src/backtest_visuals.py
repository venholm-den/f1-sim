from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


DARK_BG = "#2F3542"
PANEL_BG = "#3A4050"
HEADER_BG = "#D9DCE2"
TEXT_LIGHT = "#F5F7FA"
TEXT_DARK = "#111827"
ROW_A = "#F8FAFC"
ROW_B = "#EEF2F7"
GOOD_BG = "#D7F5DF"
BAD_BG = "#F7D6D6"
WARN_BG = "#FFF0C2"
BORDER = "#111827"


def _prepare_output_path(output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _as_percent(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""

    if not np.isfinite(number):
        return ""

    return f"{number:.0%}"


def _as_number(value: Any, decimals: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""

    if not np.isfinite(number):
        return ""

    return f"{number:.{decimals}f}"


def _yes_no(value: Any) -> str:
    if isinstance(value, str):
        return "Yes" if value.strip().lower() in {"true", "yes", "1"} else "No"
    return "Yes" if bool(value) else "No"


def _truncate(value: Any, limit: int = 28) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"


def _format_strategy(value: Any, limit: int = 32) -> str:
    text = str(value or "")
    text = text.replace("-", "-")
    return _truncate(text, limit=limit)


def _draw_table(
    display: pd.DataFrame,
    output_path: str | Path,
    title: str,
    subtitle: str | None = None,
    highlight_columns: dict[str, str] | None = None,
    figsize_width: float = 18.0,
) -> str:
    output_path = _prepare_output_path(output_path)
    highlight_columns = highlight_columns or {}

    n_rows = len(display)
    fig_height = max(5.5, min(18, 0.42 * n_rows + 2.4))

    fig, ax = plt.subplots(figsize=(figsize_width, fig_height))
    fig.patch.set_facecolor(DARK_BG)
    ax.set_facecolor(DARK_BG)
    ax.axis("off")

    table = ax.table(
        cellText=display.values,
        colLabels=display.columns,
        loc="center",
        cellLoc="left",
        colLoc="left",
    )

    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    table.scale(1, 1.45)

    col_names = list(display.columns)

    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor(BORDER)
        cell.set_linewidth(1.0)

        if row == 0:
            cell.set_facecolor(HEADER_BG)
            cell.set_text_props(weight="bold", color=TEXT_DARK)
            continue

        cell.set_facecolor(ROW_A if row % 2 else ROW_B)
        cell.set_text_props(color=TEXT_DARK)

    for col_name, mode in highlight_columns.items():
        if col_name not in col_names:
            continue

        col_idx = col_names.index(col_name)

        for row_idx in range(1, n_rows + 1):
            value = str(display.iloc[row_idx - 1, col_idx]).strip().lower()

            if mode == "yes_no":
                table[(row_idx, col_idx)].set_facecolor(GOOD_BG if value == "yes" else BAD_BG)
            elif mode == "error":
                try:
                    number = abs(float(value))
                except ValueError:
                    number = 0.0
                if number <= 1:
                    table[(row_idx, col_idx)].set_facecolor(GOOD_BG)
                elif number <= 3:
                    table[(row_idx, col_idx)].set_facecolor(WARN_BG)
                else:
                    table[(row_idx, col_idx)].set_facecolor(BAD_BG)
            elif mode == "score":
                try:
                    number = float(value.replace("%", ""))
                except ValueError:
                    number = 0.0
                if number >= 75:
                    table[(row_idx, col_idx)].set_facecolor(GOOD_BG)
                elif number >= 40:
                    table[(row_idx, col_idx)].set_facecolor(WARN_BG)
                else:
                    table[(row_idx, col_idx)].set_facecolor(BAD_BG)

    fig.text(0.025, 0.965, title, fontsize=22, weight="bold", color=TEXT_LIGHT, ha="left", va="top")

    if subtitle:
        fig.text(0.025, 0.925, subtitle, fontsize=11, color="#D1D5DB", ha="left", va="top")

    plt.tight_layout(rect=[0.0, 0.0, 1.0, 0.90])
    plt.savefig(output_path, dpi=180, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

    return str(output_path)


def make_strategy_comparison_png(
    comparison: pd.DataFrame,
    output_path: str | Path,
    title: str,
) -> str:
    if comparison is None or comparison.empty:
        raise ValueError("Strategy comparison dataframe is empty.")

    display = comparison.copy()

    required = [
        "Driver",
        "predicted_strategy_sequence",
        "actual_strategy_sequence",
        "predicted_stops",
        "actual_stops",
        "stops_match",
        "exact_strategy_match",
        "strategy_score",
    ]

    missing = [column for column in required if column not in display.columns]
    if missing:
        raise ValueError(f"Missing strategy comparison columns: {missing}")

    display = display[
        [
            "Driver",
            "predicted_strategy_sequence",
            "actual_strategy_sequence",
            "predicted_stops",
            "actual_stops",
            "stops_match",
            "exact_strategy_match",
            "strategy_score",
        ]
    ].rename(
        columns={
            "predicted_strategy_sequence": "Predicted",
            "actual_strategy_sequence": "Actual",
            "predicted_stops": "Pred stops",
            "actual_stops": "Actual stops",
            "stops_match": "Stops OK",
            "exact_strategy_match": "Exact",
            "strategy_score": "Score",
        }
    )

    display["Predicted"] = display["Predicted"].map(lambda value: _format_strategy(value, 34))
    display["Actual"] = display["Actual"].map(lambda value: _format_strategy(value, 34))
    display["Pred stops"] = display["Pred stops"].map(lambda value: _as_number(value, 0))
    display["Actual stops"] = display["Actual stops"].map(lambda value: _as_number(value, 0))
    display["Stops OK"] = display["Stops OK"].map(_yes_no)
    display["Exact"] = display["Exact"].map(_yes_no)
    display["Score"] = display["Score"].map(_as_percent)

    return _draw_table(
        display=display,
        output_path=output_path,
        title=title,
        subtitle="Actual strategy is reconstructed from FastF1 race lap/stint compound data, not FIA/Pirelli barcode allocation data.",
        highlight_columns={"Stops OK": "yes_no", "Exact": "yes_no", "Score": "score"},
        figsize_width=18.0,
    )


def make_finish_comparison_png(
    comparison: pd.DataFrame,
    output_path: str | Path,
    title: str,
) -> str:
    if comparison is None or comparison.empty:
        raise ValueError("Backtest comparison dataframe is empty.")

    display = comparison.copy()

    required = ["Driver", "predicted_finish", "actual_position", "finish_abs_error"]
    missing = [column for column in required if column not in display.columns]
    if missing:
        raise ValueError(f"Missing finish comparison columns: {missing}")

    columns = ["Driver", "predicted_finish", "actual_position", "finish_abs_error"]

    if "predicted_points" in display.columns:
        columns.append("predicted_points")
    if "actual_points" in display.columns:
        columns.append("actual_points")
    if "points_abs_error" in display.columns:
        columns.append("points_abs_error")

    display = display[columns].rename(
        columns={
            "predicted_finish": "Pred finish",
            "actual_position": "Actual",
            "finish_abs_error": "Finish error",
            "predicted_points": "Pred pts",
            "actual_points": "Actual pts",
            "points_abs_error": "Pts error",
        }
    )

    for col in ["Pred finish", "Actual", "Finish error", "Pred pts", "Actual pts", "Pts error"]:
        if col in display.columns:
            decimals = 0 if col == "Actual" else 2
            display[col] = display[col].map(lambda value, d=decimals: _as_number(value, d))

    return _draw_table(
        display=display,
        output_path=output_path,
        title=title,
        subtitle="Prediction backtest by finishing position and points.",
        highlight_columns={"Finish error": "error", "Pts error": "error"},
        figsize_width=14.0,
    )


def _metrics_to_display(metrics: pd.DataFrame | dict[str, Any], strategy_metrics: pd.DataFrame | None = None) -> pd.DataFrame:
    if isinstance(metrics, pd.DataFrame):
        row = metrics.iloc[0].to_dict() if not metrics.empty else {}
    else:
        row = dict(metrics)

    strategy_row = strategy_metrics.iloc[0].to_dict() if strategy_metrics is not None and not strategy_metrics.empty else {}

    items: list[tuple[str, str]] = []

    def add_number(label: str, key: str, decimals: int = 2) -> None:
        if key in row:
            items.append((label, _as_number(row.get(key), decimals)))

    def add_percent(label: str, source: dict[str, Any], key: str) -> None:
        if key in source:
            items.append((label, _as_percent(source.get(key))))

    if "drivers_compared" in row:
        items.append(("Drivers compared", str(row.get("drivers_compared"))))

    add_number("Finish MAE", "finish_mae", 2)
    add_number("Finish RMSE", "finish_rmse", 2)
    add_number("Finish Spearman", "finish_spearman", 2)
    add_number("Points MAE", "points_mae", 2)
    add_number("Fantasy MAE", "fantasy_basic_mae", 2)

    if "top3_overlap" in row:
        items.append(("Top 3 overlap", _as_percent(row.get("top3_overlap"))))
    if "top10_overlap" in row:
        items.append(("Top 10 overlap", _as_percent(row.get("top10_overlap"))))

    add_percent("Strategy exact accuracy", strategy_row, "exact_strategy_accuracy")
    add_percent("Strategy stop accuracy", strategy_row, "stop_count_accuracy")
    add_percent("Strategy average score", strategy_row, "average_strategy_score")

    if "predicted_winner" in row:
        items.append(("Predicted winner", str(row.get("predicted_winner"))))
    if "actual_winner" in row:
        items.append(("Actual winner", str(row.get("actual_winner"))))
    if "predicted_winner_hit" in row:
        items.append(("Winner hit", "Yes" if int(row.get("predicted_winner_hit") or 0) == 1 else "No"))

    return pd.DataFrame(items, columns=["Metric", "Value"])


def make_backtest_metrics_png(
    metrics: pd.DataFrame | dict[str, Any],
    output_path: str | Path,
    title: str,
    strategy_metrics: pd.DataFrame | None = None,
) -> str:
    display = _metrics_to_display(metrics, strategy_metrics=strategy_metrics)

    if display.empty:
        raise ValueError("No metrics available for metrics PNG.")

    return _draw_table(
        display=display,
        output_path=output_path,
        title=title,
        subtitle="Headline prediction and tyre-strategy backtest metrics.",
        highlight_columns={},
        figsize_width=10.0,
    )
