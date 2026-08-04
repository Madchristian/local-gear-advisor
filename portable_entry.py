from __future__ import annotations

from collections.abc import Callable


def _show_startup_error(message: str) -> None:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    try:
        messagebox.showerror("Local Gear Advisor", message, parent=root)
    finally:
        root.destroy()


def run(
    *,
    entry: Callable[[], int] | None = None,
    show_error: Callable[[str], None] = _show_startup_error,
) -> int:
    try:
        if entry is None:
            from local_gear_advisor.portable import main

            entry = main
        return entry()
    except Exception as exc:
        message = f"Local Gear Advisor konnte nicht gestartet werden:\n\n{exc}"
        try:
            show_error(message)
        except Exception:  # noqa: S110 - no output channel remains if the dialog fails
            pass
        return 1

if __name__ == "__main__":
    raise SystemExit(run())
