import importlib
import tkinter as tk
from pathlib import Path

from local_gear_advisor import gui


class _FakeText:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.state = "disabled"

    def get(self, _start: str, _end: str) -> str:
        return self.text

    def configure(self, **kwargs) -> None:
        self.state = kwargs.get("state", self.state)

    def delete(self, _start: str, _end: str) -> None:
        self.text = ""

    def insert(self, _start: str, text: str) -> None:
        self.text = text


class _FakeButton:
    def __init__(self) -> None:
        self.state = "disabled"

    def configure(self, **kwargs) -> None:
        self.state = kwargs.get("state", self.state)


class _FakeRoot:
    def __init__(self) -> None:
        self.clipboard = None
        self.clear_calls = 0

    def clipboard_clear(self) -> None:
        self.clear_calls += 1
        self.clipboard = ""

    def clipboard_append(self, text: str) -> None:
        self.clipboard = text


def test_gui_import_has_no_tk_or_file_side_effects() -> None:
    before = tk._default_root
    module = importlib.import_module("local_gear_advisor.gui")

    assert module is not None
    assert tk._default_root is before


def test_simulationcraft_download_opens_only_the_official_https_page() -> None:
    opened: list[str] = []

    result = gui.open_simulationcraft_download(lambda url: opened.append(url) or True)

    assert result is True
    assert opened == ["https://www.simulationcraft.org/download.html"]


def test_simulationcraft_download_reports_browser_failure() -> None:
    def fail(_url: str) -> bool:
        raise OSError("no browser")

    assert gui.open_simulationcraft_download(fail) is False


def test_gui_exposes_a_simulationcraft_download_button() -> None:
    source = (Path(__file__).parents[1] / "src" / "local_gear_advisor" / "gui.py").read_text(
        encoding="utf-8"
    )

    assert 'text="SimulationCraft herunterladen…"' in source
    assert "command=open_simc_download" in source


def test_gui_worker_uses_queue_and_close_guard() -> None:
    source = (Path(__file__).parents[1] / "src" / "local_gear_advisor" / "gui.py").read_text(
        encoding="utf-8"
    )

    assert "result_queue.put" in source
    assert "root.after(0, finish_" not in source
    assert "daemon=False" in source
    assert 'root.protocol("WM_DELETE_WINDOW", request_close)' in source
    assert "if analysis_running:" in source
    assert "min_item_level_var = tk.IntVar(value=282)" in source
    assert "min_item_level=min_item_level_var.get()" in source
    assert "auto_install_var = tk.BooleanVar(value=False)" in source
    analyze_section = source[
        source.index("    def analyze()") : source.index("    def request_close()")
    ]
    assert "nonlocal analysis_running, pending_summary" in analyze_section
    assert "pending_summary = None" in analyze_section
    assert "Mindest-Itemlevel" in source
    assert "Itemlevel {summary.min_item_level}" in source
    assert "Itemlevel {min_item_level_var.get()}" not in source
    assert source.count("Nur offensiver DPS-Vergleich") == 3


def test_gui_shows_copyable_import_text_after_successful_analysis() -> None:
    source = (Path(__file__).parents[1] / "src" / "local_gear_advisor" / "gui.py").read_text(
        encoding="utf-8"
    )

    assert "import_text_widget" in source
    assert 'text="Importtext kopieren"' in source
    assert "root.clipboard_clear()" in source
    assert "root.clipboard_append(" in source
    assert "summary.transport_text" in source
    # The copy handler must read live from the widget, not from a stale closure
    # variable, and must never claim success without real clipboard content.
    copy_section = source[source.index("def copy_import_text()") : source.index("def analyze()")]
    assert "_copy_import_text_to_clipboard(root, import_text_widget)" in copy_section
    # Failed analyses must not leave a stale/misleading import text visible.
    assert "def finish_error(exc: Exception) -> None:" in source
    error_section = source[
        source.index("def finish_error(exc: Exception) -> None:") : source.index("def analyze()")
    ]
    assert "import_text_widget" in error_section


def test_import_transport_widget_success_and_error_states_are_behavioral() -> None:
    widget = _FakeText("stale")
    button = _FakeButton()

    gui._set_import_transport(widget, button, "LGA2:new")
    assert widget.text == "LGA2:new"
    assert widget.state == "disabled"
    assert button.state == "normal"

    gui._set_import_transport(widget, button, None)
    assert widget.text == ""
    assert widget.state == "disabled"
    assert button.state == "disabled"


def test_copy_import_transport_reads_widget_and_calls_real_clipboard_adapter() -> None:
    root = _FakeRoot()
    widget = _FakeText("  LGA2:payload  \n")

    copied = gui._copy_import_text_to_clipboard(root, widget)

    assert copied is True
    assert root.clear_calls == 1
    assert root.clipboard == "LGA2:payload"


def test_copy_import_transport_refuses_empty_widget_without_touching_clipboard() -> None:
    root = _FakeRoot()

    copied = gui._copy_import_text_to_clipboard(root, _FakeText(" \n"))

    assert copied is False
    assert root.clear_calls == 0
    assert root.clipboard is None
