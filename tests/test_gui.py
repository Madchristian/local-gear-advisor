import importlib
import tkinter as tk
from pathlib import Path


def test_gui_import_has_no_tk_or_file_side_effects() -> None:
    before = tk._default_root
    module = importlib.import_module("local_gear_advisor.gui")

    assert module is not None
    assert tk._default_root is before


def test_gui_worker_uses_queue_and_close_guard() -> None:
    source = (Path(__file__).parents[1] / "src" / "local_gear_advisor" / "gui.py").read_text(
        encoding="utf-8"
    )

    assert "result_queue.put" in source
    assert "root.after(0, finish_" not in source
    assert "daemon=False" in source
    assert 'root.protocol("WM_DELETE_WINDOW", request_close)' in source
    assert "if analysis_running:" in source
