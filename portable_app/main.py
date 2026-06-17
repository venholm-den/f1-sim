from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QPixmap, QTextCursor
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
    QScrollArea,
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
from src.app_services.output_index import OutputFile, list_core_outputs, list_visual_outputs, read_output_table
from src.app_services.run_service import run_pipeline_with_config


SESSION_OPTIONS = ["Q", "SQ", "S", "FP3", "FP2", "FP1", "R"]


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


class RaceSetupScreen(QWidget):
    run_requested = Signal()

    def __init__(self, settings: PortableRunSettings) -> None:
        super().__init__()

        self.year = QSpinBox()
        self.year.setRange(1950, 2100)
        self.year.setValue(settings.year)

        self.event_field = QLineEdit(settings.event)

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

        self.overtaking = QSpinBox()
        self.overtaking.setRange(0, 100)
        self.overtaking.setSuffix("%")
        self.overtaking.setValue(int(settings.default_overtaking_difficulty * 100))

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
        form.addRow("Default overtaking difficulty", self.overtaking)

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

        help_box = QLabel(
            "MVP note: this screen writes a temporary run config and executes the existing "
            "simulation pipeline in the background."
        )
        help_box.setWordWrap(True)
        help_box.setObjectName("mutedText")

        layout = QVBoxLayout(self)
        layout.addWidget(title_label("Race Setup", "Configure and run the local simulator."))
        layout.addWidget(form_box)
        layout.addWidget(options_box)
        layout.addLayout(actions)
        layout.addWidget(help_box)
        layout.addStretch()

    def _browse_output_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select output directory", self.output_dir.text())

        if selected:
            self.output_dir.setText(selected)

    def settings(self) -> PortableRunSettings:
        return PortableRunSettings(
            year=int(self.year.value()),
            event=self.event_field.text().strip() or "latest",
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

        self.visual_tabs = QTabWidget()
        self.visual_labels: dict[str, QLabel] = {}
        self.files_table = QTableWidget()
        self.summary_table = QTableWidget()
        self.strategy_table = QTableWidget()

        refresh = QPushButton("Refresh Outputs")
        refresh.clicked.connect(self.refresh)
        open_output = QPushButton("Open Output Folder")
        open_output.clicked.connect(lambda: open_path(self.output_dir))

        actions = QHBoxLayout()
        actions.addWidget(refresh)
        actions.addWidget(open_output)
        actions.addStretch()

        tables = QWidget()
        tables_layout = QVBoxLayout(tables)
        tables_layout.setContentsMargins(0, 0, 0, 0)
        tables_layout.addWidget(QLabel("Simulation Summary"))
        tables_layout.addWidget(self.summary_table)
        tables_layout.addWidget(QLabel("Strategy Recommendations"))
        tables_layout.addWidget(self.strategy_table)

        layout = QVBoxLayout(self)
        layout.addWidget(title_label("Results", "Review generated visual reports and output tables."))
        layout.addLayout(actions)
        layout.addWidget(QLabel("Visual Outputs"))
        layout.addWidget(self.visual_tabs, stretch=3)
        layout.addWidget(QLabel("Tables"))
        layout.addWidget(tables, stretch=2)
        layout.addWidget(QLabel("Output Files"))
        layout.addWidget(self.files_table)
        self.refresh()

    def set_output_dir(self, output_dir: str) -> None:
        self.output_dir = output_dir
        self.refresh()

    def refresh(self) -> None:
        files = list_core_outputs(self.output_dir)
        visuals = list_visual_outputs(self.output_dir)
        self._refresh_visuals(visuals)
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
        strategy = read_output_table(
            self.output_dir,
            "strategy/predicted_tyre_strategy_history_adjusted.csv",
            max_rows=20,
        )

        if strategy.empty:
            strategy = read_output_table(self.output_dir, "strategy/predicted_tyre_strategy.csv", max_rows=20)

        set_table_frame(self.summary_table, summary)
        set_table_frame(self.strategy_table, strategy)

    def _refresh_visuals(self, visuals: list[OutputFile]) -> None:
        self.visual_tabs.clear()
        self.visual_labels.clear()

        found = [visual for visual in visuals if visual.exists]

        if not found:
            empty = QLabel("No report images found yet. Run a simulation with report images enabled.")
            empty.setObjectName("mutedText")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.visual_tabs.addTab(empty, "No Images")
            return

        for visual in found:
            label = QLabel()
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setObjectName("imagePreview")
            label.setMinimumHeight(360)

            pixmap = QPixmap(visual.path)
            if pixmap.isNull():
                label.setText(f"Could not load image: {visual.path}")
                label.setObjectName("mutedText")
            else:
                label.setPixmap(
                    pixmap.scaledToWidth(
                        1050,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(label)
            self.visual_tabs.addTab(scroll, visual.label)
            self.visual_labels[visual.label] = label


class ModelSignalsScreen(QWidget):
    def __init__(self, output_dir: str) -> None:
        super().__init__()
        self.output_dir = output_dir

        self.status_label = QLabel()
        self.status_label.setObjectName("mutedText")
        self.status_label.setWordWrap(True)
        self.overview_table = QTableWidget()
        self.driver_table = QTableWidget()
        self.driver_table.setMinimumHeight(280)
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
        layout.addWidget(overview_box)
        layout.addWidget(driver_box)
        layout.addWidget(commentary_box)
        self.refresh()

    def set_output_dir(self, output_dir: str) -> None:
        self.output_dir = output_dir
        self.refresh()

    def refresh(self) -> None:
        signals = load_model_signals(self.output_dir)
        status = "found" if signals.features_exist else "missing"
        self.status_label.setText(f"driver_model_features.csv is {status}: {signals.features_path}")
        set_table_frame(self.overview_table, signals.overview)
        set_table_frame(self.driver_table, signals.driver_signals, max_rows=50)
        self.commentary.setPlainText(signals.commentary or "No model commentary file found yet.")


class PlaceholderScreen(QWidget):
    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        label = QLabel(body)
        label.setWordWrap(True)
        label.setObjectName("mutedText")
        layout = QVBoxLayout(self)
        layout.addWidget(title_label(title, "Planned for the next build phase."))
        layout.addWidget(label)
        layout.addStretch()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Race Simulator Portable MVP")
        self.resize(1280, 820)
        self.thread: QThread | None = None
        self.worker: RunWorker | None = None

        self.base_config = load_json_config(DEFAULT_CONFIG_PATH)
        settings = settings_from_config(self.base_config)

        self.stack = QStackedWidget()
        self.sidebar_buttons: list[SidebarButton] = []
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(150)

        self.race_setup = RaceSetupScreen(settings)
        self.data_sources = DataSourcesScreen(self.base_config)
        self.model_signals = ModelSignalsScreen(settings.output_dir)
        self.results = ResultsScreen(settings.output_dir)

        self.screens = [
            ("Race Setup", self.race_setup),
            ("Data Sources", self.data_sources),
            ("Model Signals", self.model_signals),
            (
                "Weather & Reliability",
                PlaceholderScreen(
                    "Weather & Reliability",
                    "MVP placeholder. The Results screen already reads the generated reliability "
                    "profile; a dedicated dashboard can be layered on next.",
                ),
            ),
            (
                "Tyre Strategy",
                PlaceholderScreen(
                    "Tyre Strategy",
                    "MVP placeholder. Candidate strategy scores are available in the strategy CSV.",
                ),
            ),
            (
                "Fantasy",
                PlaceholderScreen(
                    "Fantasy",
                    "MVP placeholder. Fantasy tables can be read from simulation_summary.csv.",
                ),
            ),
            ("Results", self.results),
            (
                "Compare",
                PlaceholderScreen(
                    "Compare",
                    "MVP placeholder. Scenario presets and run queues belong in phase two.",
                ),
            ),
            (
                "Settings",
                PlaceholderScreen(
                    "Settings",
                    "MVP placeholder. App settings should live in app_settings.json.",
                ),
            ),
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
        self.stack.setCurrentIndex(index)

        for button_index, button in enumerate(self.sidebar_buttons):
            button.setChecked(button_index == index)

    def _append_log(self, text: str) -> None:
        self.log.moveCursor(QTextCursor.MoveOperation.End)
        self.log.insertPlainText(text)
        self.log.moveCursor(QTextCursor.MoveOperation.End)

    def _current_config(self) -> dict[str, Any]:
        return build_run_config(self.base_config, self.race_setup.settings())

    def _start_run(self) -> None:
        if self.thread is not None:
            QMessageBox.warning(self, "Run in progress", "A simulation is already running.")
            return

        config = self._current_config()
        self.data_sources.set_config(config)
        self.model_signals.set_output_dir(self.race_setup.settings().output_dir)
        self.results.set_output_dir(self.race_setup.settings().output_dir)
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
        self.model_signals.set_output_dir(self.race_setup.settings().output_dir)
        self.results.set_output_dir(self.race_setup.settings().output_dir)
        self._select_screen(6)

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
