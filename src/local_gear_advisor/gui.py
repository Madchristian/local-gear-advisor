from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .cli import DEFAULT_RESULTS, DEFAULT_RUN_ROOT
from .pipeline import AnalysisSummary, analyze_export
from .profilesets import SimSettings


def launch() -> None:
    root = tk.Tk()
    root.title("Local Gear Advisor")
    root.geometry("820x700")
    root.minsize(680, 560)

    outer = ttk.Frame(root, padding=12)
    outer.pack(fill="both", expand=True)
    outer.columnconfigure(1, weight=1)
    outer.rowconfigure(5, weight=1)

    simc_var = tk.StringVar()
    iterations_var = tk.IntVar(value=1000)
    fight_var = tk.StringVar(value="Patchwerk")
    status_var = tk.StringVar(value="Bereit – beim Start wurden keine Dateien verändert.")
    result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
    analysis_running = False

    ttk.Label(outer, text="simc.exe").grid(row=0, column=0, sticky="w", padx=(0, 8))
    simc_entry = ttk.Entry(outer, textvariable=simc_var)
    simc_entry.grid(row=0, column=1, sticky="ew")

    def choose_simc() -> None:
        path = filedialog.askopenfilename(
            title="simc.exe auswählen",
            filetypes=[("SimulationCraft", "simc.exe"), ("EXE", "*.exe")],
        )
        if path:
            simc_var.set(path)

    ttk.Button(outer, text="Auswählen…", command=choose_simc).grid(row=0, column=2, padx=(8, 0))

    ttk.Label(outer, text="Szenario").grid(row=1, column=0, sticky="w", pady=(10, 0))
    ttk.Combobox(
        outer,
        textvariable=fight_var,
        values=("Patchwerk", "DungeonSlice"),
        state="readonly",
        width=20,
    ).grid(row=1, column=1, sticky="w", pady=(10, 0))

    ttk.Label(outer, text="Iterationen").grid(row=2, column=0, sticky="w", pady=(10, 0))
    ttk.Spinbox(outer, from_=100, to=1000000, textvariable=iterations_var, width=14).grid(
        row=2, column=1, sticky="w", pady=(10, 0)
    )

    ttk.Label(outer, text="/simc-Export (mit Taschen)").grid(
        row=4, column=0, columnspan=3, sticky="w", pady=(14, 4)
    )
    export_text = tk.Text(outer, wrap="none", undo=True)
    export_text.grid(row=5, column=0, columnspan=3, sticky="nsew")

    def load_export() -> None:
        path = filedialog.askopenfilename(
            title="Gespeicherten /simc-Export laden",
            filetypes=[("SimC profile", "*.simc"), ("Text", "*.txt"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Lesefehler", str(exc), parent=root)
            return
        export_text.delete("1.0", "end")
        export_text.insert("1.0", content)

    controls = ttk.Frame(outer)
    controls.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(10, 0))
    ttk.Button(controls, text="Export laden…", command=load_export).pack(side="left")

    analyze_button = ttk.Button(controls, text="Lokal analysieren")
    analyze_button.pack(side="right")
    ttk.Label(outer, textvariable=status_var, wraplength=760).grid(
        row=7, column=0, columnspan=3, sticky="ew", pady=(10, 0)
    )
    ttk.Label(
        outer,
        text=f"Staging-Ergebnis: {DEFAULT_RESULTS}\nKeine automatische Installation in WoW.",
        foreground="#666666",
    ).grid(row=8, column=0, columnspan=3, sticky="w", pady=(8, 0))

    def finish_success(summary: AnalysisSummary) -> None:
        nonlocal analysis_running
        analysis_running = False
        analyze_button.configure(state="normal")
        status_var.set(
            f"Fertig: {summary.candidate_count} Items, {summary.variant_count} Varianten, "
            f"SimC {summary.simc_version}."
        )
        messagebox.showinfo(
            "Analyse abgeschlossen",
            f"Die geprüfte Results.lua wurde im Projekt erzeugt:\n{summary.results_path}",
            parent=root,
        )

    def finish_error(exc: Exception) -> None:
        nonlocal analysis_running
        analysis_running = False
        analyze_button.configure(state="normal")
        status_var.set(f"Fehler: {exc}")
        messagebox.showerror("Analyse fehlgeschlagen", str(exc), parent=root)

    def analyze() -> None:
        nonlocal analysis_running
        raw = export_text.get("1.0", "end-1c")
        executable = Path(simc_var.get().strip())
        if not raw.strip():
            messagebox.showwarning(
                "Export fehlt", "Bitte den vollständigen /simc-Export einfügen.", parent=root
            )
            return
        if not executable.is_file():
            messagebox.showwarning(
                "simc.exe fehlt", "Bitte eine vorhandene simc.exe auswählen.", parent=root
            )
            return
        try:
            settings = SimSettings(
                iterations=iterations_var.get(),
                fight_style=fight_var.get(),
            )
        except (ValueError, tk.TclError) as exc:
            messagebox.showwarning("Ungültige Einstellungen", str(exc), parent=root)
            return
        analysis_running = True
        analyze_button.configure(state="disabled")
        status_var.set("Simulation läuft …")

        def worker() -> None:
            try:
                summary = analyze_export(
                    export_text=raw,
                    executable=executable,
                    settings=settings,
                    results_path=DEFAULT_RESULTS,
                    run_root=DEFAULT_RUN_ROOT,
                )
            except Exception as exc:
                result_queue.put(("error", exc))
            else:
                result_queue.put(("success", summary))

        threading.Thread(target=worker, daemon=False, name="simc-analysis").start()

    def poll_results() -> None:
        try:
            kind, payload = result_queue.get_nowait()
        except queue.Empty:
            root.after(100, poll_results)
            return
        if kind == "success" and isinstance(payload, AnalysisSummary):
            finish_success(payload)
        elif kind == "error" and isinstance(payload, Exception):
            finish_error(payload)
        else:
            finish_error(RuntimeError("Ungültiges Ergebnis vom Analyse-Thread"))
        root.after(100, poll_results)

    def request_close() -> None:
        if analysis_running:
            messagebox.showinfo(
                "Simulation läuft",
                "Bitte warten, bis SimulationCraft beendet ist. "
                "Das Fenster bleibt aus Sicherheitsgründen geöffnet.",
                parent=root,
            )
            return
        root.destroy()

    analyze_button.configure(command=analyze)
    root.protocol("WM_DELETE_WINDOW", request_close)
    root.after(100, poll_results)
    root.mainloop()
