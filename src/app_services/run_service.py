from __future__ import annotations

import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Callable


class CallbackWriter:
    def __init__(self, callback: Callable[[str], None]) -> None:
        self.callback = callback

    def write(self, text: str) -> int:
        if text:
            self.callback(text)

        return len(text)

    def flush(self) -> None:
        return None


def run_pipeline_with_config(
    config_path: str | Path,
    log_callback: Callable[[str], None],
) -> int:
    argv = sys.argv[:]
    writer = CallbackWriter(log_callback)

    try:
        import main as pipeline_main

        sys.argv = ["main.py", "--config", str(config_path)]

        with redirect_stdout(writer), redirect_stderr(writer):
            pipeline_main.main()

        return 0
    except Exception:
        log_callback(traceback.format_exc())
        return 1
    finally:
        sys.argv = argv
