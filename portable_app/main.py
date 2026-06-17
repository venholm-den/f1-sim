from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter, QPen, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.app_services.config_service import (
    DEFAULT_CONFIG_PATH,
    PortableRunSettings,
    build_run_config,
    load_json_config,
    settings_from_config,
    write_temp_run_config,
)
from src.app_services.data_health import DataSourceStatus, read_csv_preview, validate_data_sources
from src.app_services.model_signals import load_model_signals
from src.app_services.output_index import list_core_outputs, read_output_table
from src.app_services.run_service import run_pipeline_with_config


SESSION_OPTIONS = ["Q", "SQ", "S", "FP3", "FP2", "FP1", "R"]
TRACK_LAYOUT_CACHE: dict[tuple[int, str, str], list[tuple[float, float, float]]] = {}


def season_options(default_year: int) -> list[str]:
    current_year = pd.Timestamp.now().year
    first_year = min(2018, default_year)
    final_year = max(current_year + 1, default_year)
    return [str(year) for year in range(final_year, first_year - 1, -1)]


def available_event_names(year: int) -> list[str]:
    try:
        import fastf1

        fastf1.Cache.enable_cache(str(project_root() / "data" / "cache"))
        schedule = fastf1.get_event_schedule(year)
    except Exception:
        return []

    if schedule.empty or "EventName" not in schedule.columns:
        return []

    if "RoundNumber" in schedule.columns:
        schedule = schedule[pd.to_numeric(schedule["RoundNumber"], errors="coerce").fillna(0).gt(0)]

    return [str(name) for name in schedule["EventName"].dropna().unique().tolist()]


def read_first_output_table(
    output_dir: str | Path,
    relative_paths: list[str],
    max_rows: int = 200,
) -> pd.DataFrame:
    for relative_path in relative_paths:
        frame = read_output_table(output_dir, relative_path, max_rows=max_rows)

        if not frame.empty:
            return frame

    return pd.DataFrame()


def select_columns(frame: pd.DataFrame, columns: list[str], max_rows: int = 100) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    selected = [column for column in columns if column in frame.columns]

    if not selected:
        return frame.head(max_rows)

    return frame[selected].head(max_rows)


def sorted_view(
    frame: pd.DataFrame,
    columns: list[str],
    sort_by: str,
    ascending: bool = False,
    max_rows: int = 20,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    output = frame.copy()

    if sort_by in output.columns:
        output["_sort_value"] = pd.to_numeric(output[sort_by], errors="coerce")
        output = output.sort_values("_sort_value", ascending=ascending, na_position="last")
        output = output.drop(columns=["_sort_value"])

    return select_columns(output, columns, max_rows=max_rows)


def chart_points(
    frame: pd.DataFrame,
    label_column: str,
    value_column: str,
    max_items: int = 8,
    multiplier: float = 1.0,
) -> list[tuple[str, float]]:
    if frame.empty or label_column not in frame.columns or value_column not in frame.columns:
        return []

    values = frame[[label_column, value_column]].copy()
    values[value_column] = pd.to_numeric(values[value_column], errors="coerce") * multiplier
    values = values.dropna(subset=[value_column])
    values = values.sort_values(value_column, ascending=False).head(max_items)

    return [
        (str(row[label_column]), float(row[value_column]))
        for _, row in values.iterrows()
    ]


def sector_leaders(output_dir: str | Path) -> dict[str, tuple[str, float]]:
    laps = read_output_table(output_dir, "lap_details/weekend_lap_details.csv", max_rows=20_000)

    if laps.empty:
        return {}

    if "CleanPushLap" in laps.columns:
        clean = laps["CleanPushLap"].astype(str).str.lower().isin(["true", "1"])
        laps = laps[clean]

    leaders: dict[str, tuple[str, float]] = {}

    for label, column in [("S1", "Sector1Seconds"), ("S2", "Sector2Seconds"), ("S3", "Sector3Seconds")]:
        if column not in laps.columns or "Driver" not in laps.columns:
            continue

        sector = laps[["Driver", column]].copy()
        sector[column] = pd.to_numeric(sector[column], errors="coerce")
        sector = sector.dropna(subset=[column]).sort_values(column)

        if not sector.empty:
            leaders[label] = (str(sector.iloc[0]["Driver"]), float(sector.iloc[0][column]))

    return leaders


def track_layout_points(
    output_dir: str | Path,
    year: int | None = None,
    event_name: str | None = None,
    session_name: str | None = None,
) -> list[tuple[float, float, float]]:
    laps = read_output_table(output_dir, "lap_details/weekend_lap_details.csv", max_rows=5_000)

    if laps.empty and (year is None or not event_name):
        return []

    year_value = pd.to_numeric(laps.get("Year", pd.Series(dtype="float64")), errors="coerce").dropna()
    event_value = laps.get("Event", pd.Series(dtype="object")).dropna()
    session_value = laps.get("Session", pd.Series(dtype="object")).dropna()

    if year is None and not year_value.empty:
        year = int(year_value.iloc[0])
    if not event_name and not event_value.empty:
        event_name = str(event_value.iloc[0])
    if not session_name and not session_value.empty:
        session_name = str(session_value.iloc[0])

    if year is None or not event_name or event_name == "latest":
        return []

    session_name = session_name or "Q"
    cache_key = (year, event_name, session_name)

    if cache_key in TRACK_LAYOUT_CACHE:
        return TRACK_LAYOUT_CACHE[cache_key]

    try:
        import fastf1

        fastf1.Cache.enable_cache(str(project_root() / "data" / "cache"))
        session = fastf1.get_session(year, event_name, session_name)
        session.load(laps=True, telemetry=True, weather=False, messages=False)
        telemetry = session.laps.pick_fastest().get_telemetry().add_distance()
    except Exception:
        TRACK_LAYOUT_CACHE[cache_key] = []
        return []

    required = {"X", "Y", "Distance"}
    if telemetry.empty or not required.issubset(set(telemetry.columns)):
        TRACK_LAYOUT_CACHE[cache_key] = []
        return []

    frame = telemetry[["X", "Y", "Distance"]].dropna().copy()

    if frame.empty:
        TRACK_LAYOUT_CACHE[cache_key] = []
        return []

    max_distance = pd.to_numeric(frame["Distance"], errors="coerce").max()
    if not pd.notna(max_distance) or float(max_distance) <= 0:
        TRACK_LAYOUT_CACHE[cache_key] = []
        return []

    step = max(1, len(frame) // 420)
    sampled = frame.iloc[::step].copy()
    points = [
        (float(row["X"]), float(row["Y"]), float(row["Distance"]) / float(max_distance))
        for _, row in sampled.iterrows()
    ]
    TRACK_LAYOUT_CACHE[cache_key] = points
    return points


def weather_risk_summary(output_dir: str | Path) -> dict[str, float | str]:
    summary = read_output_table(output_dir, "simulation_summary.csv", max_rows=100)
    commentary_path = Path(output_dir) / "report" / "model_commentary.txt"
    text = commentary_path.read_text(encoding="utf-8") if commentary_path.exists() else ""
    values: dict[str, float | str] = {
        "rain": 0.0,
        "chaos": 0.0,
        "dnf": 0.0,
        "degradation": 0.0,
        "uncertainty": 0.0,
        "source": "No forecast output saved",
    }

    if not summary.empty:
        if "red_flag_chance" in summary.columns:
            values["chaos"] = float(pd.to_numeric(summary["red_flag_chance"], errors="coerce").mean() * 100)
        if "dnf_chance" in summary.columns:
            values["dnf"] = float(pd.to_numeric(summary["dnf_chance"], errors="coerce").mean() * 100)
        if "performance_uncertainty" in summary.columns:
            values["uncertainty"] = float(pd.to_numeric(summary["performance_uncertainty"], errors="coerce").mean() * 100)
        if "tyre_deg_score" in summary.columns:
            values["degradation"] = float(pd.to_numeric(summary["tyre_deg_score"], errors="coerce").mean() * 100)

    for line in text.splitlines():
        if line.lower().startswith("weather modifiers:"):
            values["source"] = line
            break

    if "rain" in text.lower() or "wet" in text.lower():
        values["rain"] = max(float(values["rain"]), 55.0)

    return values


def completed_race_review(output_dir: str | Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    root = Path(output_dir)
    actual = read_output_table(root, "backtest/latest_prediction_snapshot_actual_results.csv", max_rows=100)
    strategy = read_output_table(root, "backtest/latest_prediction_snapshot_actual_strategy.csv", max_rows=100)
    comparison = read_output_table(root, "backtest/latest_prediction_snapshot_comparison.csv", max_rows=100)
    laps = read_output_table(root, "lap_details/weekend_lap_details.csv", max_rows=20_000)
    rows: list[dict[str, str]] = []

    if not actual.empty and "actual_position" in actual.columns:
        winner = actual.copy()
        winner["actual_position"] = pd.to_numeric(winner["actual_position"], errors="coerce")
        winner = winner.sort_values("actual_position")

        if not winner.empty:
            rows.append({"Metric": "Race winner", "Value": str(winner.iloc[0].get("Driver", "")), "Source": "actual results"})

    lap_scope = laps[laps["Session"].astype(str).eq("R")] if "Session" in laps.columns else laps

    if lap_scope.empty:
        lap_scope = laps

    for metric, column in [
        ("Fastest lap", "LapTimeSeconds"),
        ("Best sector 1", "Sector1Seconds"),
        ("Best sector 2", "Sector2Seconds"),
        ("Best sector 3", "Sector3Seconds"),
    ]:
        if column in lap_scope.columns and "Driver" in lap_scope.columns:
            values = lap_scope[["Driver", column]].copy()
            values[column] = pd.to_numeric(values[column], errors="coerce")
            values = values.dropna(subset=[column]).sort_values(column)

            if not values.empty:
                rows.append(
                    {
                        "Metric": metric,
                        "Value": f"{values.iloc[0]['Driver']} ({float(values.iloc[0][column]):.3f}s)",
                        "Source": "lap details",
                    }
                )

    if comparison.empty:
        outliers = pd.DataFrame()
    else:
        outliers = sorted_view(
            comparison,
            [
                "Driver",
                "Team",
                "predicted_finish",
                "actual_position",
                "finish_error",
                "finish_abs_error",
                "actual_status",
                "dnf_chance",
            ],
            sort_by="finish_abs_error",
            max_rows=20,
        )

    return pd.DataFrame(rows), select_columns(strategy, ["Driver", "Team", "actual_strategy", "actual_stops", "actual_race_laps"]), outliers


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def open_path(path: str | Path) -> None:
    resolved = Path(path).resolve()

    if sys.platform.startswith("win"):
        os.startfile(resolved)  # type: ignore[attr-defined]
    else:
        QDesktopServices.openUrl(resolved.as_uri())


def set_table_frame(table: QTableWidget, frame: pd.DataFrame, max_rows: int = 100) -> None:
    preview = frame.head(max_rows).copy()
    table.clear()
    table.setRowCount(len(preview))
    table.setColumnCount(len(preview.columns))
    table.setHorizontalHeaderLabels([str(column) for column in preview.columns])

    for row_index, (_, row) in enumerate(preview.iterrows()):
        for column_index, value in enumerate(row):
            table.setItem(row_index, column_index, QTableWidgetItem(str(value)))

    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)


class BarChartWidget(QWidget):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.title = title
        self.points: list[tuple[str, float]] = []
        self.setMinimumHeight(230)

    def set_points(self, points: list[tuple[str, float]]) -> None:
        self.points = points
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0d131c"))
        painter.setPen(QColor("#f5f7fb"))
        painter.drawText(18, 26, self.title)

        if not self.points:
            painter.setPen(QColor("#aab3c2"))
            painter.drawText(18, 72, "No data available yet.")
            return

        max_value = max(value for _, value in self.points) or 1.0
        left = 130
        right_pad = 70
        top = 48
        row_height = max(20, min(30, (self.height() - top - 20) // max(1, len(self.points))))
        bar_max = max(80, self.width() - left - right_pad)

        for index, (label, value) in enumerate(self.points):
            y = top + index * row_height
            width = int(bar_max * max(0.0, value) / max_value)
            painter.setPen(QColor("#aab3c2"))
            painter.drawText(18, y + 16, label[:14])
            painter.setPen(QPen(QColor("#ef233c"), 1))
            painter.setBrush(QColor("#ef233c"))
            painter.drawRoundedRect(left, y + 4, width, row_height - 9, 3, 3)
            painter.setPen(QColor("#f5f7fb"))
            painter.drawText(left + width + 8, y + 16, f"{value:.1f}")


class TrackSectorWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.sectors: dict[str, tuple[str, float]] = {}
        self.layout_points: list[tuple[float, float, float]] = []
        self.setMinimumHeight(260)

    def set_track(self, sectors: dict[str, tuple[str, float]], layout_points: list[tuple[float, float, float]]) -> None:
        self.sectors = sectors
        self.layout_points = layout_points
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0d131c"))
        painter.setPen(QColor("#f5f7fb"))
        painter.drawText(18, 26, "Track sector dominance")

        if not self.sectors and not self.layout_points:
            painter.setPen(QColor("#aab3c2"))
            painter.drawText(18, 72, "No sector timing data found yet.")
            return

        colors = {"S1": "#ef233c", "S2": "#f59e0b", "S3": "#38bdf8"}

        if self.layout_points:
            xs = [point[0] for point in self.layout_points]
            ys = [point[1] for point in self.layout_points]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            span_x = max(max_x - min_x, 1.0)
            span_y = max(max_y - min_y, 1.0)
            pad_x = 44
            pad_top = 46
            pad_bottom = 88
            draw_width = max(120, self.width() - pad_x * 2)
            draw_height = max(120, self.height() - pad_top - pad_bottom)

            def scale(point: tuple[float, float, float]) -> tuple[int, int]:
                x, y, _ = point
                sx = pad_x + int((x - min_x) / span_x * draw_width)
                sy = pad_top + int((max_y - y) / span_y * draw_height)
                return sx, sy

            for start, end in zip(self.layout_points, self.layout_points[1:]):
                sector = "S1" if start[2] < 1 / 3 else "S2" if start[2] < 2 / 3 else "S3"
                x1, y1 = scale(start)
                x2, y2 = scale(end)
                painter.setPen(QPen(QColor(colors[sector]), 6))
                painter.drawLine(x1, y1, x2, y2)
        else:
            painter.setPen(QColor("#aab3c2"))
            painter.drawText(18, 56, "Real circuit layout unavailable; showing sector winners only.")

        legend_y = self.height() - 54
        for index, sector in enumerate(["S1", "S2", "S3"]):
            x = 22 + index * max(170, (self.width() - 44) // 3)
            driver, seconds = self.sectors.get(sector, ("n/a", 0.0))
            painter.setPen(QPen(QColor(colors[sector]), 8))
            painter.drawLine(x, legend_y, x + 36, legend_y)
            painter.setPen(QColor("#f5f7fb"))
            painter.drawText(x, legend_y + 24, f"{sector}: {driver}")
            painter.setPen(QColor("#aab3c2"))
            label = f"{seconds:.3f}s" if seconds else "no time"
            painter.drawText(x, legend_y + 42, label)


class WeatherForecastWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, float | str] = {}
        self.setMinimumHeight(260)

    def set_values(self, values: dict[str, float | str]) -> None:
        self.values = values
        self.update()

    def _value(self, key: str) -> float:
        value = self.values.get(key, 0.0)

        try:
            number = float(value)
            if not pd.notna(number):
                return 0.0
            return max(0.0, min(100.0, number))
        except Exception:
            return 0.0

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0d131c"))
        painter.setPen(QColor("#f5f7fb"))
        painter.drawText(18, 26, "Forecast and weather-risk graphic")

        rows = [
            ("Rain/Wet signal", "rain", "#38bdf8"),
            ("Chaos/red flag", "chaos", "#ef233c"),
            ("DNF pressure", "dnf", "#f97316"),
            ("Tyre degradation", "degradation", "#f59e0b"),
            ("Uncertainty", "uncertainty", "#818cf8"),
        ]
        left = 150
        top = 54
        bar_width = max(80, self.width() - left - 80)

        for index, (label, key, color) in enumerate(rows):
            value = self._value(key)
            y = top + index * 32
            painter.setPen(QColor("#aab3c2"))
            painter.drawText(18, y + 16, label)
            painter.setPen(QPen(QColor("#263242"), 1))
            painter.setBrush(QColor("#111821"))
            painter.drawRoundedRect(left, y + 4, bar_width, 14, 3, 3)
            painter.setPen(QPen(QColor(color), 1))
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(left, y + 4, int(bar_width * value / 100), 14, 3, 3)
            painter.setPen(QColor("#f5f7fb"))
            painter.drawText(left + bar_width + 10, y + 16, f"{value:.0f}%")

        painter.setPen(QColor("#aab3c2"))
        source = str(self.values.get("source", "No forecast output saved"))
        painter.drawText(18, self.height() - 24, source[:145])


class RunWorker(QObject):
    log = Signal(str)
    finished = Signal(int)

    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self.config_path = config_path

    def run(self) -> None:
        exit_code = run_pipeline_with_config(self.config_path, self.log.emit)
        self.finished.emit(exit_code)


class SidebarButton(QPushButton):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setCheckable(True)
        self.setMinimumHeight(42)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class SummaryStrip(QWidget):
    def __init__(self, config: dict[str, Any], settings: PortableRunSettings) -> None:
        super().__init__()
        self.values: dict[str, QLabel] = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)

        for key, label in [
            ("event", "EVENT"),
            ("session", "SESSION"),
            ("model", "MODEL VERSION"),
            ("weather", "WEATHER SOURCE"),
        ]:
            card = QFrame()
            card.setObjectName("summaryCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 8, 12, 8)
            label_widget = QLabel(label)
            label_widget.setObjectName("summaryLabel")
            value_widget = QLabel()
            value_widget.setObjectName("summaryValue")
            value_widget.setWordWrap(True)
            card_layout.addWidget(label_widget)
            card_layout.addWidget(value_widget)
            self.values[key] = value_widget
            layout.addWidget(card)

        layout.addStretch()
        self.update_context(config, settings)

    def update_context(self, config: dict[str, Any], settings: PortableRunSettings) -> None:
        model = config.get("model", {})
        weather_source = "Forecast + FastF1" if model.get("use_weather_forecast", True) else "FastF1"
        self.values["event"].setText(settings.event)
        self.values["session"].setText(settings.session)
        self.values["model"].setText(str(model.get("model_version", "unknown")))
        self.values["weather"].setText(weather_source)


class RaceSetupScreen(QWidget):
    run_requested = Signal()

    def __init__(self, settings: PortableRunSettings) -> None:
        super().__init__()

        self.year = QComboBox()
        self.year.addItems(season_options(settings.year))
        self.year.setCurrentText(str(settings.year))

        self.event_field = QComboBox()
        self.event_field.setEditable(True)
        self._refresh_event_options(settings.event)
        self.year.currentTextChanged.connect(lambda: self._refresh_event_options(self.event_field.currentText()))

        self.session_combo = QComboBox()
        self.session_combo.addItems(SESSION_OPTIONS)
        self.session_combo.setCurrentText(settings.session if settings.session in SESSION_OPTIONS else "Q")

        self.n_sims = QSpinBox()
        self.n_sims.setRange(1, 1_000_000)
        self.n_sims.setSingleStep(1000)
        self.n_sims.setValue(settings.n_sims)

        self.random_seed = QSpinBox()
        self.random_seed.setRange(0, 999_999_999)
        self.random_seed.setValue(settings.random_seed)

        self.baseline_races = QSpinBox()
        self.baseline_races.setRange(0, 30)
        self.baseline_races.setValue(settings.n_baseline_races)

        self.strategy_lookback = QSpinBox()
        self.strategy_lookback.setRange(0, 20)
        self.strategy_lookback.setValue(settings.historical_strategy_lookback_years)

        self.overtaking = QSlider(Qt.Orientation.Horizontal)
        self.overtaking.setRange(0, 100)
        self.overtaking.setValue(int(settings.default_overtaking_difficulty * 100))
        self.overtaking_value = QLabel(f"{self.overtaking.value()}%")
        self.overtaking_value.setMinimumWidth(44)
        self.overtaking.valueChanged.connect(lambda value: self.overtaking_value.setText(f"{value}%"))

        self.output_dir = QLineEdit(settings.output_dir)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse_output_dir)

        self.save_snapshot = QCheckBox("Save prediction snapshot")
        self.save_snapshot.setChecked(settings.save_prediction_snapshot)
        self.save_images = QCheckBox("Save report images")
        self.save_images.setChecked(settings.save_report_images)
        self.save_raw = QCheckBox("Save raw results")
        self.save_raw.setChecked(settings.save_raw_results)
        self.post_discord = QCheckBox("Post to Discord")
        self.post_discord.setChecked(settings.post_to_discord)
        self.use_forecast = QCheckBox("Use weather forecast fallback")
        self.use_forecast.setChecked(settings.use_weather_forecast)
        self.use_race_control = QCheckBox("Use race-control context")
        self.use_race_control.setChecked(settings.use_race_control_context)
        self.use_track_red_flags = QCheckBox("Use track red-flag baseline")
        self.use_track_red_flags.setChecked(settings.use_track_red_flag_base_chance)

        run_button = QPushButton("Run Simulation")
        run_button.setObjectName("primaryButton")
        run_button.setMinimumHeight(46)
        run_button.clicked.connect(self.run_requested.emit)

        open_output = QPushButton("Open Output Folder")
        open_output.clicked.connect(lambda: open_path(self.output_dir.text() or "outputs"))

        form_box = QGroupBox("Simulation Parameters")
        form = QFormLayout(form_box)
        form.addRow("Season", self.year)
        form.addRow("Event", self.event_field)
        form.addRow("Session", self.session_combo)
        form.addRow("Simulation count", self.n_sims)
        form.addRow("Random seed", self.random_seed)
        form.addRow("Baseline races", self.baseline_races)
        form.addRow("Historical strategy lookback", self.strategy_lookback)
        overtaking_row = QHBoxLayout()
        overtaking_row.addWidget(QLabel("Easier"))
        overtaking_row.addWidget(self.overtaking)
        overtaking_row.addWidget(QLabel("Harder"))
        overtaking_row.addWidget(self.overtaking_value)
        form.addRow("Default overtaking difficulty", overtaking_row)

        output_row = QHBoxLayout()
        output_row.addWidget(self.output_dir)
        output_row.addWidget(browse)
        form.addRow("Output directory", output_row)

        options_box = QGroupBox("Outputs and Model Switches")
        options_layout = QGridLayout(options_box)
        for index, widget in enumerate(
            [
                self.save_snapshot,
                self.save_images,
                self.save_raw,
                self.post_discord,
                self.use_forecast,
                self.use_race_control,
                self.use_track_red_flags,
            ]
        ):
            options_layout.addWidget(widget, index // 2, index % 2)

        actions = QHBoxLayout()
        actions.addWidget(run_button)
        actions.addWidget(open_output)
        actions.addStretch()

        status_box = QGroupBox("Ready to Run")
        status_layout = QGridLayout(status_box)
        ready = QLabel("All required parameters are set.")
        ready.setObjectName("statusReady")
        status_layout.addWidget(ready, 0, 0, 1, 3)
        status_layout.addWidget(QLabel("Estimated Duration"), 1, 0)
        status_layout.addWidget(QLabel("Depends on cache/network"), 2, 0)
        status_layout.addWidget(QLabel("Simulations"), 1, 1)
        status_layout.addWidget(QLabel(f"{settings.n_sims:,}"), 2, 1)
        status_layout.addWidget(QLabel("Storage"), 1, 2)
        status_layout.addWidget(QLabel("CSV + dashboard data"), 2, 2)

        help_box = QLabel(
            "About this setup: higher simulation counts improve stability but increase run time. "
            "Use a fixed random seed for reproducible results."
        )
        help_box.setWordWrap(True)
        help_box.setObjectName("mutedText")

        layout = QVBoxLayout(self)
        layout.addWidget(title_label("Race Setup", "Configure and run the local simulator."))
        layout.addWidget(form_box)
        layout.addWidget(options_box)
        layout.addLayout(actions)
        layout.addWidget(status_box)
        layout.addWidget(help_box)
        layout.addStretch()

    def _browse_output_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select output directory", self.output_dir.text())

        if selected:
            self.output_dir.setText(selected)

    def _refresh_event_options(self, preferred_event: str = "") -> None:
        current = str(preferred_event or "").strip()
        try:
            year = int(self.year.currentText())
        except ValueError:
            year = pd.Timestamp.now().year

        event_names = available_event_names(year)
        options = ["latest", *event_names]

        if current and current not in options:
            options.insert(1, current)

        self.event_field.blockSignals(True)
        self.event_field.clear()
        self.event_field.addItems(options)
        self.event_field.setCurrentText(current or "latest")
        self.event_field.blockSignals(False)

    def settings(self) -> PortableRunSettings:
        return PortableRunSettings(
            year=int(self.year.currentText()),
            event=self.event_field.currentText().strip() or "latest",
            session=self.session_combo.currentText().strip() or "Q",
            n_sims=int(self.n_sims.value()),
            random_seed=int(self.random_seed.value()),
            n_baseline_races=int(self.baseline_races.value()),
            historical_strategy_lookback_years=int(self.strategy_lookback.value()),
            default_overtaking_difficulty=float(self.overtaking.value() / 100),
            output_dir=self.output_dir.text().strip() or "outputs",
            save_prediction_snapshot=self.save_snapshot.isChecked(),
            save_report_images=self.save_images.isChecked(),
            save_raw_results=self.save_raw.isChecked(),
            post_to_discord=self.post_discord.isChecked(),
            use_weather_forecast=self.use_forecast.isChecked(),
            use_race_control_context=self.use_race_control.isChecked(),
            use_track_red_flag_base_chance=self.use_track_red_flags.isChecked(),
        )


class DataSourcesScreen(QWidget):
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__()
        self.config = config
        self.statuses: list[DataSourceStatus] = []

        self.status_table = QTableWidget()
        self.preview_table = QTableWidget()
        self.preview_table.setMinimumHeight(260)

        reload_button = QPushButton("Reload / Validate")
        reload_button.clicked.connect(self.refresh)
        open_data = QPushButton("Open Data Folder")
        open_data.clicked.connect(lambda: open_path("data"))

        actions = QHBoxLayout()
        actions.addWidget(reload_button)
        actions.addWidget(open_data)
        actions.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(title_label("Data Sources", "Validate local CSV/config inputs and preview rows."))
        layout.addLayout(actions)
        layout.addWidget(self.status_table)
        layout.addWidget(QLabel("Preview"))
        layout.addWidget(self.preview_table)
        self.status_table.itemSelectionChanged.connect(self._preview_selected)
        self.refresh()

    def set_config(self, config: dict[str, Any]) -> None:
        self.config = config
        self.refresh()

    def refresh(self) -> None:
        self.statuses = validate_data_sources(self.config)
        self.status_table.clear()
        self.status_table.setRowCount(len(self.statuses))
        self.status_table.setColumnCount(6)
        self.status_table.setHorizontalHeaderLabels(
            ["Source", "Status", "Rows", "Modified", "Path", "Message"]
        )

        for row, status in enumerate(self.statuses):
            values = [
                status.label,
                status.status,
                str(status.row_count),
                status.modified_at,
                status.path,
                status.message,
            ]

            for column, value in enumerate(values):
                self.status_table.setItem(row, column, QTableWidgetItem(value))

        self.status_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        if self.statuses:
            self.status_table.selectRow(0)

    def _preview_selected(self) -> None:
        selected = self.status_table.currentRow()

        if selected < 0 or selected >= len(self.statuses):
            return

        frame = read_csv_preview(self.statuses[selected].path)
        set_table_frame(self.preview_table, frame)


class ResultsScreen(QWidget):
    def __init__(self, output_dir: str) -> None:
        super().__init__()
        self.output_dir = output_dir

        self.win_chart = BarChartWidget("Win chance %")
        self.podium_chart = BarChartWidget("Podium chance %")
        self.fantasy_chart = BarChartWidget("Fantasy points")
        self.files_table = QTableWidget()
        self.summary_table = QTableWidget()
        self.position_table = QTableWidget()
        self.strategy_table = QTableWidget()

        refresh = QPushButton("Refresh Outputs")
        refresh.clicked.connect(self.refresh)
        open_output = QPushButton("Open Output Folder")
        open_output.clicked.connect(lambda: open_path(self.output_dir))

        actions = QHBoxLayout()
        actions.addWidget(refresh)
        actions.addWidget(open_output)
        actions.addStretch()

        charts = QWidget()
        charts_layout = QGridLayout(charts)
        charts_layout.setContentsMargins(0, 0, 0, 0)
        charts_layout.addWidget(self.win_chart, 0, 0)
        charts_layout.addWidget(self.podium_chart, 0, 1)
        charts_layout.addWidget(self.fantasy_chart, 1, 0, 1, 2)

        tabs = QTabWidget()
        tabs.addTab(self.summary_table, "Summary")
        tabs.addTab(self.position_table, "Position Matrix")
        tabs.addTab(self.strategy_table, "Strategy")
        tabs.addTab(self.files_table, "Files")

        layout = QVBoxLayout(self)
        layout.addWidget(title_label("Results", "Review native dashboards and output tables."))
        layout.addLayout(actions)
        layout.addWidget(charts, stretch=2)
        layout.addWidget(tabs, stretch=3)
        self.refresh()

    def set_output_dir(self, output_dir: str) -> None:
        self.output_dir = output_dir
        self.refresh()

    def refresh(self) -> None:
        files = list_core_outputs(self.output_dir)
        self.files_table.clear()
        self.files_table.setRowCount(len(files))
        self.files_table.setColumnCount(4)
        self.files_table.setHorizontalHeaderLabels(["Output", "Status", "Size", "Path"])

        for row, file in enumerate(files):
            values = [
                file.label,
                "found" if file.exists else "missing",
                f"{file.size_bytes:,}",
                file.path,
            ]
            for column, value in enumerate(values):
                self.files_table.setItem(row, column, QTableWidgetItem(value))

        self.files_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        summary = read_output_table(self.output_dir, "simulation_summary.csv", max_rows=20)
        full_summary = read_output_table(self.output_dir, "simulation_summary.csv", max_rows=100)
        position_matrix = read_output_table(self.output_dir, "position_matrix.csv", max_rows=30)
        strategy = read_output_table(
            self.output_dir,
            "strategy/predicted_tyre_strategy_history_adjusted.csv",
            max_rows=20,
        )

        if strategy.empty:
            strategy = read_output_table(self.output_dir, "strategy/predicted_tyre_strategy.csv", max_rows=20)

        self.win_chart.set_points(chart_points(full_summary, "Driver", "win_chance", multiplier=100))
        self.podium_chart.set_points(chart_points(full_summary, "Driver", "podium_chance", multiplier=100))
        self.fantasy_chart.set_points(chart_points(full_summary, "Driver", "avg_fantasy_points"))
        set_table_frame(
            self.summary_table,
            select_columns(
                summary,
                [
                    "Driver",
                    "Team",
                    "avg_finish",
                    "win_chance",
                    "podium_chance",
                    "dnf_chance",
                    "avg_points",
                    "avg_fantasy_points",
                    "fantasy_xppm",
                ],
                max_rows=20,
            ),
        )
        set_table_frame(self.position_table, position_matrix)
        set_table_frame(self.strategy_table, strategy)


class ModelSignalsScreen(QWidget):
    def __init__(self, output_dir: str, settings: PortableRunSettings) -> None:
        super().__init__()
        self.output_dir = output_dir
        self.year = settings.year
        self.event_name = settings.event
        self.session_name = settings.session

        self.status_label = QLabel()
        self.status_label.setObjectName("mutedText")
        self.status_label.setWordWrap(True)
        self.overview_table = QTableWidget()
        self.driver_table = QTableWidget()
        self.driver_table.setMinimumHeight(280)
        self.track_sector = TrackSectorWidget()
        self.commentary = QTextEdit()
        self.commentary.setReadOnly(True)
        self.commentary.setMinimumHeight(140)

        refresh = QPushButton("Refresh Signals")
        refresh.clicked.connect(self.refresh)
        open_output = QPushButton("Open Output Folder")
        open_output.clicked.connect(lambda: open_path(self.output_dir))

        actions = QHBoxLayout()
        actions.addWidget(refresh)
        actions.addWidget(open_output)
        actions.addStretch()

        overview_box = QGroupBox("Signal Health")
        overview_layout = QVBoxLayout(overview_box)
        overview_layout.addWidget(self.status_label)
        overview_layout.addWidget(self.overview_table)

        driver_box = QGroupBox("Driver Signal Blend")
        driver_layout = QVBoxLayout(driver_box)
        driver_layout.addWidget(self.driver_table)

        commentary_box = QGroupBox("Model Commentary")
        commentary_layout = QVBoxLayout(commentary_box)
        commentary_layout.addWidget(self.commentary)

        layout = QVBoxLayout(self)
        layout.addWidget(
            title_label(
                "Model Signals",
                "Inspect the inputs and confidence signals behind the latest prediction.",
            )
        )
        layout.addLayout(actions)
        layout.addWidget(self.track_sector, stretch=1)
        layout.addWidget(overview_box)
        layout.addWidget(driver_box)
        layout.addWidget(commentary_box)
        self.refresh()

    def set_output_dir(self, output_dir: str, settings: PortableRunSettings | None = None) -> None:
        self.output_dir = output_dir
        if settings is not None:
            self.year = settings.year
            self.event_name = settings.event
            self.session_name = settings.session
        self.refresh()

    def refresh(self) -> None:
        signals = load_model_signals(self.output_dir)
        status = "found" if signals.features_exist else "missing"
        self.status_label.setText(f"driver_model_features.csv is {status}: {signals.features_path}")
        self.track_sector.set_track(
            sector_leaders(self.output_dir),
            track_layout_points(self.output_dir, self.year, self.event_name, self.session_name),
        )
        set_table_frame(self.overview_table, signals.overview)
        set_table_frame(self.driver_table, signals.driver_signals, max_rows=50)
        self.commentary.setPlainText(signals.commentary or "No model commentary file found yet.")


class WeatherReliabilityScreen(QWidget):
    def __init__(self, output_dir: str) -> None:
        super().__init__()
        self.output_dir = output_dir
        self.dnf_chart = BarChartWidget("Driver DNF chance %")
        self.engine_chart = BarChartWidget("Engine reliability risk %")
        self.weather_forecast = WeatherForecastWidget()
        self.reliability_table = QTableWidget()
        self.summary_table = QTableWidget()

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        actions = QHBoxLayout()
        actions.addWidget(refresh)
        actions.addStretch()

        charts = QWidget()
        charts_layout = QGridLayout(charts)
        charts_layout.setContentsMargins(0, 0, 0, 0)
        charts_layout.addWidget(self.dnf_chart, 0, 0)
        charts_layout.addWidget(self.engine_chart, 0, 1)

        tabs = QTabWidget()
        tabs.addTab(self.summary_table, "Race Risk")
        tabs.addTab(self.reliability_table, "Reliability Profile")

        layout = QVBoxLayout(self)
        layout.addWidget(
            title_label(
                "Weather & Reliability",
                "Review DNF, red-flag, team, and power-unit risk signals.",
            )
        )
        layout.addLayout(actions)
        layout.addWidget(charts, stretch=2)
        layout.addWidget(self.weather_forecast, stretch=2)
        layout.addWidget(tabs, stretch=3)
        self.refresh()

    def set_output_dir(self, output_dir: str) -> None:
        self.output_dir = output_dir
        self.refresh()

    def refresh(self) -> None:
        summary = read_output_table(self.output_dir, "simulation_summary.csv", max_rows=100)
        reliability = read_output_table(self.output_dir, "debug/reliability_profile.csv", max_rows=100)
        self.dnf_chart.set_points(chart_points(summary, "Driver", "dnf_chance", multiplier=100))
        self.engine_chart.set_points(
            chart_points(reliability, "Team", "engine_reliability_score", multiplier=100)
        )
        self.weather_forecast.set_values(weather_risk_summary(self.output_dir))
        set_table_frame(
            self.summary_table,
            sorted_view(
                summary,
                [
                    "Driver",
                    "Team",
                    "dnf_chance",
                    "red_flag_chance",
                    "reliability_score",
                    "engine_reliability_score",
                    "PowerUnitSupplier",
                    "reliability_profile_source",
                ],
                sort_by="dnf_chance",
                max_rows=30,
            ),
        )
        set_table_frame(
            self.reliability_table,
            select_columns(
                reliability,
                [
                    "Team",
                    "PowerUnitSupplier",
                    "team_mechanical_dnf_rate",
                    "power_unit_mechanical_dnf_rate",
                    "engine_reliability_score",
                    "reliability_observations",
                    "reliability_profile_source",
                ],
            ),
        )


class TyreStrategyScreen(QWidget):
    def __init__(self, output_dir: str) -> None:
        super().__init__()
        self.output_dir = output_dir
        self.stop_chart = BarChartWidget("Expected stops")
        self.risk_chart = BarChartWidget("Old tyre risk")
        self.strategy_table = QTableWidget()
        self.candidates_table = QTableWidget()

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        actions = QHBoxLayout()
        actions.addWidget(refresh)
        actions.addStretch()

        charts = QWidget()
        charts_layout = QGridLayout(charts)
        charts_layout.setContentsMargins(0, 0, 0, 0)
        charts_layout.addWidget(self.stop_chart, 0, 0)
        charts_layout.addWidget(self.risk_chart, 0, 1)

        tabs = QTabWidget()
        tabs.addTab(self.strategy_table, "Strategy Picks")
        tabs.addTab(self.candidates_table, "Candidates & Reasons")

        layout = QVBoxLayout(self)
        layout.addWidget(title_label("Tyre Strategy", "Review predicted stint plans and strategy risk."))
        layout.addLayout(actions)
        layout.addWidget(charts, stretch=2)
        layout.addWidget(tabs, stretch=3)
        self.refresh()

    def set_output_dir(self, output_dir: str) -> None:
        self.output_dir = output_dir
        self.refresh()

    def refresh(self) -> None:
        strategy = read_first_output_table(
            self.output_dir,
            [
                "strategy/predicted_tyre_strategy_history_adjusted.csv",
                "strategy/predicted_tyre_strategy.csv",
            ],
        )
        self.stop_chart.set_points(chart_points(strategy, "Driver", "expected_stops"))
        self.risk_chart.set_points(chart_points(strategy, "Driver", "OldTyreRiskScore"))
        set_table_frame(
            self.strategy_table,
            select_columns(
                strategy,
                [
                    "Driver",
                    "Team",
                    "GridPosition",
                    "PredictedStrategy",
                    "expected_stops",
                    "strategy_confidence",
                    "risk_level",
                    "EstimatedDegPerLap",
                    "tyre_data_source",
                ],
            ),
        )
        set_table_frame(
            self.candidates_table,
            select_columns(
                strategy,
                [
                    "Driver",
                    "candidate_strategy_summary",
                    "strategy_reason",
                    "history_adjustment_reason",
                    "history_adjustment_blocked_reason",
                    "strategy_risk_reason",
                    "tyre_confidence_reason",
                ],
            ),
        )


class FantasyScreen(QWidget):
    def __init__(self, output_dir: str) -> None:
        super().__init__()
        self.output_dir = output_dir
        self.points_chart = BarChartWidget("Expected fantasy points")
        self.value_chart = BarChartWidget("Fantasy value xPPM")
        self.fantasy_table = QTableWidget()
        self.breakdown_table = QTableWidget()

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        actions = QHBoxLayout()
        actions.addWidget(refresh)
        actions.addStretch()

        charts = QWidget()
        charts_layout = QGridLayout(charts)
        charts_layout.setContentsMargins(0, 0, 0, 0)
        charts_layout.addWidget(self.points_chart, 0, 0)
        charts_layout.addWidget(self.value_chart, 0, 1)

        tabs = QTabWidget()
        tabs.addTab(self.fantasy_table, "Rankings")
        tabs.addTab(self.breakdown_table, "Points Breakdown")

        layout = QVBoxLayout(self)
        layout.addWidget(title_label("Fantasy", "Review expected fantasy output, floor, ceiling, and value."))
        layout.addLayout(actions)
        layout.addWidget(charts, stretch=2)
        layout.addWidget(tabs, stretch=3)
        self.refresh()

    def set_output_dir(self, output_dir: str) -> None:
        self.output_dir = output_dir
        self.refresh()

    def refresh(self) -> None:
        summary = read_output_table(self.output_dir, "simulation_summary.csv", max_rows=100)
        self.points_chart.set_points(chart_points(summary, "Driver", "avg_fantasy_points"))
        self.value_chart.set_points(chart_points(summary, "Driver", "fantasy_xppm"))
        set_table_frame(
            self.fantasy_table,
            sorted_view(
                summary,
                [
                    "Driver",
                    "Team",
                    "avg_fantasy_points",
                    "fantasy_floor_p10",
                    "fantasy_ceiling_p90",
                    "fantasy_price",
                    "fantasy_xppm",
                ],
                sort_by="avg_fantasy_points",
            ),
        )
        set_table_frame(
            self.breakdown_table,
            select_columns(
                summary,
                [
                    "Driver",
                    "avg_quali_points",
                    "avg_finish_fantasy_points",
                    "avg_position_change_points",
                    "avg_fastest_lap_points",
                    "avg_dotd_points",
                    "avg_dnf_penalty",
                ],
            ),
        )


class CompareScreen(QWidget):
    def __init__(self, output_dir: str) -> None:
        super().__init__()
        self.output_dir = output_dir
        self.delta_chart = BarChartWidget("Finish delta vs latest snapshot")
        self.compare_table = QTableWidget()
        self.snapshot_table = QTableWidget()

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        actions = QHBoxLayout()
        actions.addWidget(refresh)
        actions.addStretch()

        tabs = QTabWidget()
        tabs.addTab(self.compare_table, "Current vs Snapshot")
        tabs.addTab(self.snapshot_table, "Snapshots")

        layout = QVBoxLayout(self)
        layout.addWidget(title_label("Compare", "Compare the current output to saved prediction snapshots."))
        layout.addLayout(actions)
        layout.addWidget(self.delta_chart, stretch=2)
        layout.addWidget(tabs, stretch=3)
        self.refresh()

    def set_output_dir(self, output_dir: str) -> None:
        self.output_dir = output_dir
        self.refresh()

    def refresh(self) -> None:
        root = Path(self.output_dir)
        current = read_output_table(root, "simulation_summary.csv", max_rows=100)
        snapshot = read_output_table(root, "history/latest_prediction_snapshot.csv", max_rows=100)
        snapshots = sorted((root / "history").glob("*prediction_snapshot*.csv")) if (root / "history").exists() else []

        if current.empty or snapshot.empty or "Driver" not in current.columns or "Driver" not in snapshot.columns:
            comparison = pd.DataFrame()
        else:
            merged = current.merge(
                snapshot,
                on="Driver",
                suffixes=("_current", "_snapshot"),
            )
            comparison = pd.DataFrame(
                {
                    "Driver": merged["Driver"],
                    "Team": merged.get("Team_current", merged.get("Team_snapshot", "")),
                    "avg_finish_current": merged.get("avg_finish_current", ""),
                    "avg_finish_snapshot": merged.get("avg_finish_snapshot", ""),
                    "finish_delta": pd.to_numeric(
                        merged.get("avg_finish_current", pd.Series(dtype=float)),
                        errors="coerce",
                    )
                    - pd.to_numeric(
                        merged.get("avg_finish_snapshot", pd.Series(dtype=float)),
                        errors="coerce",
                    ),
                    "win_chance_current": merged.get("win_chance_current", ""),
                    "win_chance_snapshot": merged.get("win_chance_snapshot", ""),
                }
            )

        chart_frame = comparison.copy()

        if not chart_frame.empty and "finish_delta" in chart_frame.columns:
            chart_frame["finish_delta_abs"] = pd.to_numeric(
                chart_frame["finish_delta"],
                errors="coerce",
            ).abs()

        self.delta_chart.set_points(chart_points(chart_frame, "Driver", "finish_delta_abs"))
        set_table_frame(self.compare_table, comparison)
        set_table_frame(
            self.snapshot_table,
            pd.DataFrame(
                [
                    {
                        "Snapshot": path.name,
                        "Modified": pd.Timestamp(path.stat().st_mtime, unit="s").strftime("%Y-%m-%d %H:%M"),
                        "Path": str(path),
                    }
                    for path in snapshots[-30:]
                ]
            ),
        )


class BacktestingScreen(QWidget):
    def __init__(self, output_dir: str) -> None:
        super().__init__()
        self.output_dir = output_dir
        self.error_chart = BarChartWidget("Largest finish prediction errors")
        self.metrics_table = QTableWidget()
        self.comparison_table = QTableWidget()
        self.strategy_table = QTableWidget()
        self.snapshot_table = QTableWidget()
        self.recommendations = QTextEdit()
        self.recommendations.setReadOnly(True)

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        actions = QHBoxLayout()
        actions.addWidget(refresh)
        actions.addStretch()

        tabs = QTabWidget()
        tabs.addTab(self.metrics_table, "Accuracy Metrics")
        tabs.addTab(self.comparison_table, "Prediction vs Actual")
        tabs.addTab(self.strategy_table, "Strategy Backtest")
        tabs.addTab(self.snapshot_table, "Snapshots")
        tabs.addTab(self.recommendations, "Insights")

        layout = QVBoxLayout(self)
        layout.addWidget(
            title_label(
                "Backtesting",
                "Compare saved predictions against actual race results and calibration reports.",
            )
        )
        layout.addLayout(actions)
        layout.addWidget(self.error_chart, stretch=2)
        layout.addWidget(tabs, stretch=3)
        self.refresh()

    def set_output_dir(self, output_dir: str) -> None:
        self.output_dir = output_dir
        self.refresh()

    def refresh(self) -> None:
        root = Path(self.output_dir)
        metrics = read_output_table(root, "backtest/latest_prediction_snapshot_metrics.csv", max_rows=100)
        comparison = read_output_table(root, "backtest/latest_prediction_snapshot_comparison.csv", max_rows=100)
        strategy = read_output_table(root, "backtest/latest_prediction_snapshot_strategy_metrics.csv", max_rows=100)
        recommendation_path = root / "backtest" / "latest_prediction_snapshot_recommendations.txt"
        snapshots = sorted((root / "history").glob("*prediction_snapshot*.csv")) if (root / "history").exists() else []

        chart_frame = comparison.copy()
        error_column = ""

        for candidate in ["finish_abs_error", "prediction_error", "finish_error"]:
            if candidate in chart_frame.columns:
                error_column = candidate
                break

        if error_column:
            chart_frame["prediction_error_abs"] = pd.to_numeric(
                chart_frame[error_column],
                errors="coerce",
            ).abs()

        self.error_chart.set_points(chart_points(chart_frame, "Driver", "prediction_error_abs"))
        set_table_frame(self.metrics_table, metrics)
        set_table_frame(self.comparison_table, comparison)
        set_table_frame(self.strategy_table, strategy)
        set_table_frame(
            self.snapshot_table,
            pd.DataFrame(
                [
                    {
                        "Snapshot": path.name,
                        "Modified": pd.Timestamp(path.stat().st_mtime, unit="s").strftime("%Y-%m-%d %H:%M"),
                        "Path": str(path),
                    }
                    for path in snapshots[-40:]
                ]
            ),
        )

        if recommendation_path.exists():
            try:
                self.recommendations.setPlainText(recommendation_path.read_text(encoding="utf-8"))
            except Exception:
                self.recommendations.setPlainText("Could not read backtest recommendations.")
        else:
            self.recommendations.setPlainText("No backtest recommendations found yet.")


class RaceReviewScreen(QWidget):
    def __init__(self, output_dir: str) -> None:
        super().__init__()
        self.output_dir = output_dir
        self.status_label = QLabel()
        self.status_label.setObjectName("mutedText")
        self.status_label.setWordWrap(True)
        self.outlier_chart = BarChartWidget("Largest future-predictor outliers")
        self.overview_table = QTableWidget()
        self.strategy_table = QTableWidget()
        self.outlier_table = QTableWidget()

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        actions = QHBoxLayout()
        actions.addWidget(refresh)
        actions.addStretch()

        tabs = QTabWidget()
        tabs.addTab(self.overview_table, "Race Overview")
        tabs.addTab(self.strategy_table, "Actual Strategy")
        tabs.addTab(self.outlier_table, "Predictor Outliers")

        layout = QVBoxLayout(self)
        layout.addWidget(
            title_label(
                "Race Review",
                "Review completed-race facts, fastest sectors, actual strategy, and model miss signals.",
            )
        )
        layout.addLayout(actions)
        layout.addWidget(self.status_label)
        layout.addWidget(self.outlier_chart, stretch=2)
        layout.addWidget(tabs, stretch=3)
        self.refresh()

    def set_output_dir(self, output_dir: str) -> None:
        self.output_dir = output_dir
        self.refresh()

    def refresh(self) -> None:
        overview, strategy, outliers = completed_race_review(self.output_dir)

        if overview.empty and strategy.empty and outliers.empty:
            self.status_label.setText(
                "No completed-race review data found yet. Run or import a completed race/backtest snapshot to populate this screen."
            )
        else:
            self.status_label.setText(
                "Completed-race review is using actual results, lap details, strategy, and backtest comparison outputs where available."
            )

        chart_frame = outliers.copy()
        if "finish_abs_error" in chart_frame.columns:
            chart_frame["future_predictor_outlier"] = pd.to_numeric(
                chart_frame["finish_abs_error"],
                errors="coerce",
            ).abs()
        elif "finish_error" in chart_frame.columns:
            chart_frame["future_predictor_outlier"] = pd.to_numeric(
                chart_frame["finish_error"],
                errors="coerce",
            ).abs()

        self.outlier_chart.set_points(chart_points(chart_frame, "Driver", "future_predictor_outlier"))
        set_table_frame(self.overview_table, overview)
        set_table_frame(self.strategy_table, strategy)
        set_table_frame(self.outlier_table, outliers)


class SettingsScreen(QWidget):
    def __init__(self, config: dict[str, Any], settings: PortableRunSettings) -> None:
        super().__init__()
        self.config = config
        self.settings = settings
        self.config_text = QTextEdit()
        self.config_text.setReadOnly(True)
        self.paths_table = QTableWidget()

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        actions = QHBoxLayout()
        actions.addWidget(refresh)
        actions.addStretch()

        tabs = QTabWidget()
        tabs.addTab(self.config_text, "Current Config")
        tabs.addTab(self.paths_table, "Paths")

        layout = QVBoxLayout(self)
        layout.addWidget(title_label("Settings", "Inspect the active app configuration and bundled data paths."))
        layout.addLayout(actions)
        layout.addWidget(tabs)
        self.refresh()

    def set_config(self, config: dict[str, Any], settings: PortableRunSettings) -> None:
        self.config = config
        self.settings = settings
        self.refresh()

    def refresh(self) -> None:
        import json

        self.config_text.setPlainText(json.dumps(self.config, indent=2))
        data = self.config.get("data", {})
        rows = [
            {"Setting": "output_dir", "Value": self.settings.output_dir},
            {"Setting": "fantasy_prices_path", "Value": str(data.get("fantasy_prices_path", ""))},
            {"Setting": "track_profiles_path", "Value": str(data.get("track_profiles_path", ""))},
            {"Setting": "fia_document_index_path", "Value": str(data.get("fia_document_index_path", ""))},
            {"Setting": "team_power_units_path", "Value": str(data.get("team_power_units_path", ""))},
        ]
        set_table_frame(self.paths_table, pd.DataFrame(rows))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("F1 Race Simulator Portable")
        self.resize(1280, 820)
        self.thread: QThread | None = None
        self.worker: RunWorker | None = None

        self.base_config = load_json_config(DEFAULT_CONFIG_PATH)
        settings = settings_from_config(self.base_config)

        self.stack = QStackedWidget()
        self.sidebar_buttons: list[SidebarButton] = []
        self.summary_strip = SummaryStrip(self.base_config, settings)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(150)

        self.race_setup = RaceSetupScreen(settings)
        self.data_sources = DataSourcesScreen(self.base_config)
        self.model_signals = ModelSignalsScreen(settings.output_dir, settings)
        self.weather_reliability = WeatherReliabilityScreen(settings.output_dir)
        self.tyre_strategy = TyreStrategyScreen(settings.output_dir)
        self.fantasy = FantasyScreen(settings.output_dir)
        self.results = ResultsScreen(settings.output_dir)
        self.compare = CompareScreen(settings.output_dir)
        self.backtesting = BacktestingScreen(settings.output_dir)
        self.race_review = RaceReviewScreen(settings.output_dir)
        self.settings_screen = SettingsScreen(self.base_config, settings)

        self.screens = [
            ("Race Setup", self.race_setup),
            ("Data Sources", self.data_sources),
            ("Model Signals", self.model_signals),
            ("Weather & Reliability", self.weather_reliability),
            ("Tyre Strategy", self.tyre_strategy),
            ("Fantasy", self.fantasy),
            ("Results", self.results),
            ("Compare", self.compare),
            ("Backtesting", self.backtesting),
            ("Race Review", self.race_review),
            ("Settings", self.settings_screen),
        ]

        for _, screen in self.screens:
            self.stack.addWidget(screen)

        self.race_setup.run_requested.connect(self._start_run)
        self._build_shell()
        self._build_menu()
        self._select_screen(0)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        open_output = QAction("Open Output Folder", self)
        open_output.triggered.connect(lambda: open_path(self.race_setup.settings().output_dir))
        file_menu.addAction(open_output)

    def _build_shell(self) -> None:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(210)
        sidebar_layout = QVBoxLayout(sidebar)
        logo = QLabel("RACE SIMULATOR")
        logo.setObjectName("logo")
        sidebar_layout.addWidget(logo)

        for index, (label, _) in enumerate(self.screens):
            button = SidebarButton(label)
            button.clicked.connect(lambda checked=False, i=index: self._select_screen(i))
            self.sidebar_buttons.append(button)
            sidebar_layout.addWidget(button)

        sidebar_layout.addStretch()

        content = QVBoxLayout()
        content.addWidget(self.summary_strip)
        content.addWidget(self.stack, stretch=1)
        content.addWidget(QLabel("Run Log"))
        content.addWidget(self.log)

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(sidebar)
        content_frame = QWidget()
        content_frame.setLayout(content)
        root_layout.addWidget(content_frame, stretch=1)
        self.setCentralWidget(root)

    def _select_screen(self, index: int) -> None:
        self.summary_strip.update_context(self._current_config(), self.race_setup.settings())
        self.stack.setCurrentIndex(index)

        for button_index, button in enumerate(self.sidebar_buttons):
            button.setChecked(button_index == index)

    def _append_log(self, text: str) -> None:
        self.log.moveCursor(QTextCursor.MoveOperation.End)
        self.log.insertPlainText(text)
        self.log.moveCursor(QTextCursor.MoveOperation.End)

    def _current_config(self) -> dict[str, Any]:
        return build_run_config(self.base_config, self.race_setup.settings())

    def _set_output_dir_for_screens(self, output_dir: str) -> None:
        self.model_signals.set_output_dir(output_dir, self.race_setup.settings())
        self.weather_reliability.set_output_dir(output_dir)
        self.tyre_strategy.set_output_dir(output_dir)
        self.fantasy.set_output_dir(output_dir)
        self.results.set_output_dir(output_dir)
        self.compare.set_output_dir(output_dir)
        self.backtesting.set_output_dir(output_dir)
        self.race_review.set_output_dir(output_dir)

    def _start_run(self) -> None:
        if self.thread is not None:
            QMessageBox.warning(self, "Run in progress", "A simulation is already running.")
            return

        config = self._current_config()
        settings = self.race_setup.settings()
        self.summary_strip.update_context(config, settings)
        self.data_sources.set_config(config)
        self.settings_screen.set_config(config, settings)
        self._set_output_dir_for_screens(settings.output_dir)
        config_path = write_temp_run_config(config)
        self._append_log(f"\nStarting run with config: {config_path}\n")

        self.thread = QThread()
        self.worker = RunWorker(config_path)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self._append_log)
        self.worker.finished.connect(self._run_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()

    def _run_finished(self, exit_code: int) -> None:
        self._append_log(f"\nRun finished with exit code {exit_code}.\n")
        self._set_output_dir_for_screens(self.race_setup.settings().output_dir)

        if exit_code == 0:
            self._append_log("Simulation completed. Outputs are ready in the Results screen.\n")
            self._select_screen(6)
        else:
            self._append_log(
                "Simulation failed. Check the log above, then validate Data Sources and Settings.\n"
            )
            QMessageBox.critical(
                self,
                "Simulation failed",
                "The simulation did not complete. Check the run log for the detailed error.",
            )

    def _thread_finished(self) -> None:
        self.thread = None
        self.worker = None


def title_label(title: str, subtitle: str) -> QWidget:
    wrapper = QWidget()
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 8)
    title_widget = QLabel(title.upper())
    title_widget.setObjectName("screenTitle")
    subtitle_widget = QLabel(subtitle)
    subtitle_widget.setObjectName("mutedText")
    subtitle_widget.setWordWrap(True)
    layout.addWidget(title_widget)
    layout.addWidget(subtitle_widget)

    return wrapper


def apply_theme(app: QApplication) -> None:
    app.setStyleSheet(
        """
        QWidget {
            background: #080d13;
            color: #f5f7fb;
            font-family: Segoe UI, Arial;
            font-size: 10.5pt;
        }
        QFrame#sidebar {
            background: #05080d;
            border-right: 1px solid #202835;
        }
        QLabel#logo {
            color: #f5f7fb;
            font-size: 15pt;
            font-weight: 700;
            padding: 18px 10px;
        }
        QLabel#screenTitle {
            font-size: 23pt;
            font-weight: 800;
            letter-spacing: 1px;
        }
        QLabel#mutedText {
            color: #aab3c2;
        }
        QLabel#statusReady {
            color: #4ade80;
            font-weight: 700;
        }
        QFrame#summaryCard {
            background: #0d131c;
            border: 1px solid #253142;
            border-left: 3px solid #ef233c;
            border-radius: 6px;
        }
        QLabel#summaryLabel {
            color: #7f8b9d;
            font-size: 8.5pt;
            font-weight: 700;
        }
        QLabel#summaryValue {
            color: #ffffff;
            font-size: 10.5pt;
            font-weight: 700;
        }
        QPushButton {
            background: #111821;
            border: 1px solid #273242;
            border-radius: 4px;
            padding: 8px 12px;
        }
        QPushButton:hover {
            background: #182231;
        }
        QPushButton:checked {
            background: #3a1117;
            border-color: #ef233c;
            color: #ffffff;
        }
        QPushButton#primaryButton {
            background: #e50914;
            border-color: #ff2c35;
            font-weight: 700;
        }
        QGroupBox {
            border: 1px solid #202b3a;
            border-radius: 6px;
            margin-top: 10px;
            padding: 12px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }
        QLineEdit, QSpinBox, QComboBox, QTextEdit, QTableWidget {
            background: #0d131c;
            border: 1px solid #263242;
            border-radius: 4px;
            padding: 5px;
            selection-background-color: #e50914;
        }
        QHeaderView::section {
            background: #141c27;
            color: #f5f7fb;
            border: 1px solid #263242;
            padding: 5px;
        }
        QTableWidget {
            gridline-color: #263242;
        }
        QCheckBox {
            spacing: 8px;
        }
        QSlider::groove:horizontal {
            height: 6px;
            background: #263242;
            border-radius: 3px;
        }
        QSlider::sub-page:horizontal {
            background: #ef233c;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #f5f7fb;
            border: 1px solid #ef233c;
            width: 14px;
            margin: -5px 0;
            border-radius: 7px;
        }
        """
    )


def main() -> None:
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon())
    apply_theme(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
