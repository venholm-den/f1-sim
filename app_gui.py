from __future__ import annotations

import copy
import json
import os
import queue
import sys
import tempfile
import threading
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from tkinter import BooleanVar, IntVar, StringVar, Tk, filedialog, messagebox
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any


DEFAULT_CONFIG_PATH = Path("config/default_run_config.json")
SESSION_OPTIONS = ["Q", "SQ", "S", "FP3", "FP2", "FP1"]


@dataclass(frozen=True)
class GuiRunSettings:
    year: int
    event: str
    session: str
    n_sims: int
    random_seed: int
    n_baseline_races: int
    historical_strategy_lookback_years: int
    output_dir: str
    save_prediction_snapshot: bool
    save_report_images: bool
    save_raw_results: bool
    post_to_discord: bool


def resource_path(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)


def load_default_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    config_path = Path(path)

    if not config_path.exists():
        config_path = resource_path(*Path(path).parts)

    with config_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def build_run_config(
    base_config: dict[str, Any],
    settings: GuiRunSettings,
) -> dict[str, Any]:
    config = copy.deepcopy(base_config)
    run = config.setdefault("run", {})
    outputs = config.setdefault("outputs", {})

    run["year"] = settings.year
    run["event"] = settings.event
    run["session"] = settings.session
    run["n_sims"] = settings.n_sims
    run["random_seed"] = settings.random_seed
    run["n_baseline_races"] = settings.n_baseline_races
    run["historical_strategy_lookback_years"] = settings.historical_strategy_lookback_years

    outputs["output_dir"] = settings.output_dir
    outputs["save_prediction_snapshot"] = settings.save_prediction_snapshot
    outputs["save_report_images"] = settings.save_report_images
    outputs["save_raw_results"] = settings.save_raw_results
    outputs["post_to_discord"] = settings.post_to_discord

    return config


def write_temp_config(config: dict[str, Any]) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="f1-sim-gui-"))
    config_path = temp_dir / "run_config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config_path


class QueueWriter:
    def __init__(self, log_queue: queue.Queue[str]) -> None:
        self.log_queue = log_queue

    def write(self, text: str) -> int:
        if text:
            self.log_queue.put(text)
        return len(text)

    def flush(self) -> None:
        return None


class F1SimApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("F1 Simulation Runner")
        self.root.geometry("980x720")
        self.root.minsize(860, 600)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker: threading.Thread | None = None

        base_config = load_default_config()
        run = base_config.get("run", {})
        outputs = base_config.get("outputs", {})

        self.year = IntVar(value=int(run.get("year", 2026)))
        self.event = StringVar(value=str(run.get("event", "latest")))
        self.session = StringVar(value=str(run.get("session", "Q")))
        self.n_sims = IntVar(value=int(run.get("n_sims", 50000)))
        self.random_seed = IntVar(value=int(run.get("random_seed", 42)))
        self.n_baseline_races = IntVar(value=int(run.get("n_baseline_races", 5)))
        self.strategy_lookback = IntVar(
            value=int(run.get("historical_strategy_lookback_years", 5))
        )
        self.output_dir = StringVar(value=str(outputs.get("output_dir", "outputs")))
        self.save_snapshot = BooleanVar(value=bool(outputs.get("save_prediction_snapshot", True)))
        self.save_images = BooleanVar(value=bool(outputs.get("save_report_images", True)))
        self.save_raw = BooleanVar(value=bool(outputs.get("save_raw_results", True)))
        self.post_discord = BooleanVar(value=bool(outputs.get("post_to_discord", False)))

        self.base_config = base_config
        self._build_layout()
        self._poll_log_queue()

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        form = ttk.Frame(self.root, padding=12)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        self._add_labeled_entry(form, "Year", self.year, 0, 0)
        self._add_labeled_entry(form, "Event", self.event, 0, 2)

        ttk.Label(form, text="Session").grid(row=1, column=0, sticky="w", pady=4)
        session_combo = ttk.Combobox(
            form,
            textvariable=self.session,
            values=SESSION_OPTIONS,
            width=10,
            state="readonly",
        )
        session_combo.grid(row=1, column=1, sticky="w", pady=4)

        self._add_labeled_entry(form, "Simulations", self.n_sims, 1, 2)
        self._add_labeled_entry(form, "Seed", self.random_seed, 2, 0)
        self._add_labeled_entry(form, "Baseline races", self.n_baseline_races, 2, 2)
        self._add_labeled_entry(form, "Strategy lookback", self.strategy_lookback, 3, 0)

        ttk.Label(form, text="Output folder").grid(row=3, column=2, sticky="w", pady=4)
        output_frame = ttk.Frame(form)
        output_frame.grid(row=3, column=3, sticky="ew", pady=4)
        output_frame.columnconfigure(0, weight=1)
        ttk.Entry(output_frame, textvariable=self.output_dir).grid(row=0, column=0, sticky="ew")
        ttk.Button(output_frame, text="Browse", command=self._browse_output_dir).grid(
            row=0,
            column=1,
            padx=(6, 0),
        )

        checks = ttk.Frame(form)
        checks.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(8, 0))

        ttk.Checkbutton(checks, text="Save snapshot", variable=self.save_snapshot).pack(side="left")
        ttk.Checkbutton(checks, text="Save report images", variable=self.save_images).pack(
            side="left",
            padx=(14, 0),
        )
        ttk.Checkbutton(checks, text="Save raw results", variable=self.save_raw).pack(
            side="left",
            padx=(14, 0),
        )
        ttk.Checkbutton(checks, text="Post to Discord", variable=self.post_discord).pack(
            side="left",
            padx=(14, 0),
        )

        buttons = ttk.Frame(form)
        buttons.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(12, 0))

        self.run_button = ttk.Button(buttons, text="Run Simulation", command=self._start_run)
        self.run_button.pack(side="left")
        ttk.Button(buttons, text="Open Output Folder", command=self._open_output_dir).pack(
            side="left",
            padx=(8, 0),
        )
        ttk.Button(buttons, text="Clear Log", command=self._clear_log).pack(side="left", padx=(8, 0))

        self.log = ScrolledText(self.root, wrap="word", state="disabled", font=("Consolas", 10))
        self.log.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

    def _add_labeled_entry(
        self,
        parent: ttk.Frame,
        label: str,
        variable: StringVar | IntVar,
        row: int,
        column: int,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row,
            column=column + 1,
            sticky="ew",
            pady=4,
        )

    def _settings_from_form(self) -> GuiRunSettings:
        event = self.event.get().strip() or "latest"
        session = self.session.get().strip().upper() or "Q"
        output_dir = self.output_dir.get().strip() or "outputs"

        return GuiRunSettings(
            year=int(self.year.get()),
            event=event,
            session=session,
            n_sims=int(self.n_sims.get()),
            random_seed=int(self.random_seed.get()),
            n_baseline_races=int(self.n_baseline_races.get()),
            historical_strategy_lookback_years=int(self.strategy_lookback.get()),
            output_dir=output_dir,
            save_prediction_snapshot=bool(self.save_snapshot.get()),
            save_report_images=bool(self.save_images.get()),
            save_raw_results=bool(self.save_raw.get()),
            post_to_discord=bool(self.post_discord.get()),
        )

    def _browse_output_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_dir.get() or ".")

        if selected:
            self.output_dir.set(selected)

    def _open_output_dir(self) -> None:
        path = Path(self.output_dir.get() or "outputs")
        path.mkdir(parents=True, exist_ok=True)

        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            messagebox.showinfo("Output folder", str(path.resolve()))

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _poll_log_queue(self) -> None:
        while True:
            try:
                text = self.log_queue.get_nowait()
            except queue.Empty:
                break

            self._append_log(text)

        if self.worker and not self.worker.is_alive():
            self.run_button.configure(state="normal")
            self.worker = None

        self.root.after(100, self._poll_log_queue)

    def _start_run(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Simulation running", "A simulation is already running.")
            return

        try:
            settings = self._settings_from_form()
        except Exception as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        self.run_button.configure(state="disabled")
        self._append_log("\n=== Starting simulation ===\n")

        self.worker = threading.Thread(
            target=self._run_pipeline_worker,
            args=(settings,),
            daemon=True,
        )
        self.worker.start()

    def _run_pipeline_worker(self, settings: GuiRunSettings) -> None:
        writer = QueueWriter(self.log_queue)

        try:
            config = build_run_config(self.base_config, settings)
            config_path = write_temp_config(config)
            self.log_queue.put(f"Using temporary config: {config_path}\n")

            import main as simulation_main

            old_argv = sys.argv[:]
            sys.argv = ["main.py", "--config", str(config_path)]

            try:
                with redirect_stdout(writer), redirect_stderr(writer):
                    simulation_main.main()
            finally:
                sys.argv = old_argv

            self.log_queue.put("\n=== Simulation complete ===\n")
        except Exception:
            self.log_queue.put("\n=== Simulation failed ===\n")
            self.log_queue.put(traceback.format_exc())


def main() -> None:
    root = Tk()
    F1SimApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
