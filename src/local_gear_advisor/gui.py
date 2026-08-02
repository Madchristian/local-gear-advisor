from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .cli import DEFAULT_DEPLOY_RECEIPT, DEFAULT_RESULTS, DEFAULT_RUN_ROOT
from .deploy_results import (
    DeployError,
    DeployReceipt,
    expected_addon_assets,
    publish_results_live,
    utc_timestamp,
)
from .pipeline import AnalysisSummary, analyze_export
from .profilesets import SimSettings


def discover_addon_directory() -> Path | None:
    candidates: set[Path] = set()
    configured = os.environ.get("LOCAL_GEAR_ADVISOR_ADDON_DIR")
    if configured:
        candidates.add(Path(configured))
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        for prefix in ("World of Warcraft", "Program Files (x86)/World of Warcraft"):
            candidates.add(Path(f"{letter}:/{prefix}/_retail_/Interface/AddOns/LocalGearAdvisor"))
    existing = sorted(path for path in candidates if path.is_dir())
    return existing[0] if len(existing) == 1 else None


def deploy_completed_analysis(summary: AnalysisSummary, addon_dir: Path) -> DeployReceipt:
    core, toc = expected_addon_assets()
    return publish_results_live(
        staged_results=summary.results_path,
        canonical_state_path=summary.state_path,
        expected_staged_sha256=summary.results_sha256,
        addon_dir=addon_dir,
        expected_core=core,
        expected_toc=toc,
        receipt_path=DEFAULT_DEPLOY_RECEIPT,
        timestamp=utc_timestamp(),
    )


def launch() -> None:
    root = tk.Tk()
    root.title("Local Gear Advisor")
    root.geometry("820x700")
    root.minsize(680, 560)

    outer = ttk.Frame(root, padding=12)
    outer.pack(fill="both", expand=True)
    outer.columnconfigure(1, weight=1)
    outer.rowconfigure(6, weight=1)

    simc_var = tk.StringVar()
    detected_addon = discover_addon_directory()
    addon_var = tk.StringVar(value=str(detected_addon) if detected_addon else "")
    auto_install_var = tk.BooleanVar(value=False)
    iterations_var = tk.IntVar(value=1000)
    min_item_level_var = tk.IntVar(value=282)
    fight_var = tk.StringVar(value="Patchwerk")
    status_var = tk.StringVar(value="Bereit – beim Start wurden keine Dateien verändert.")
    result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
    analysis_running = False
    pending_summary: AnalysisSummary | None = None

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

    ttk.Label(outer, text="Addon-Verzeichnis").grid(
        row=1, column=0, sticky="w", padx=(0, 8), pady=(10, 0)
    )
    ttk.Entry(outer, textvariable=addon_var).grid(row=1, column=1, sticky="ew", pady=(10, 0))

    def choose_addon() -> None:
        path = filedialog.askdirectory(title="LocalGearAdvisor-Addonordner auswählen")
        if path:
            addon_var.set(path)

    ttk.Button(outer, text="Auswählen…", command=choose_addon).grid(
        row=1, column=2, padx=(8, 0), pady=(10, 0)
    )

    ttk.Label(outer, text="Szenario").grid(row=2, column=0, sticky="w", pady=(10, 0))
    ttk.Combobox(
        outer,
        textvariable=fight_var,
        values=("Patchwerk", "DungeonSlice"),
        state="readonly",
        width=20,
    ).grid(row=2, column=1, sticky="w", pady=(10, 0))

    ttk.Label(outer, text="Iterationen").grid(row=3, column=0, sticky="w", pady=(10, 0))
    ttk.Spinbox(outer, from_=100, to=1000000, textvariable=iterations_var, width=14).grid(
        row=3, column=1, sticky="w", pady=(10, 0)
    )

    ttk.Label(outer, text="Mindest-Itemlevel (0 = aus)").grid(
        row=4, column=0, sticky="w", pady=(10, 0)
    )
    ttk.Spinbox(
        outer,
        from_=0,
        to=999,
        textvariable=min_item_level_var,
        width=14,
    ).grid(row=4, column=1, sticky="w", pady=(10, 0))

    ttk.Label(outer, text="/simc-Export (mit Taschen)").grid(
        row=5, column=0, columnspan=3, sticky="w", pady=(14, 4)
    )
    export_text = tk.Text(outer, wrap="none", undo=True)
    export_text.grid(row=6, column=0, columnspan=3, sticky="nsew")

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
    controls.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(10, 0))
    ttk.Button(controls, text="Export laden…", command=load_export).pack(side="left")
    ttk.Checkbutton(
        controls,
        text="Nach Analyse sicher ins Addon installieren",
        variable=auto_install_var,
    ).pack(side="left", padx=(12, 0))

    analyze_button = ttk.Button(controls, text="Lokal analysieren")
    analyze_button.pack(side="right")
    retry_button = ttk.Button(controls, text="Jetzt installieren", state="disabled")
    retry_button.pack(side="right", padx=(0, 8))
    ttk.Label(outer, textvariable=status_var, wraplength=760).grid(
        row=8, column=0, columnspan=3, sticky="ew", pady=(10, 0)
    )
    ttk.Label(
        outer,
        text=(
            f"Staging-Ergebnis: {DEFAULT_RESULTS}\n"
            "Nur offensiver DPS-Vergleich; keine defensive Tank- oder Heilermetrik.\n"
            "Auto-Installation nur bei eindeutig geschlossenem WoW; sonst bleibt Staging erhalten."
        ),
        foreground="#666666",
    ).grid(row=9, column=0, columnspan=3, sticky="w", pady=(8, 0))

    def finish_success(
        summary: AnalysisSummary,
        *,
        receipt: DeployReceipt | None = None,
        deploy_error: Exception | None = None,
    ) -> None:
        nonlocal analysis_running, pending_summary
        analysis_running = False
        analyze_button.configure(state="normal")
        status = (
            f"Fertig: {summary.candidate_count} Items, {summary.variant_count} Varianten, "
            f"{summary.retained_profile_count} Profile, SimC {summary.simc_version}. "
            "Nur offensiver DPS-Vergleich."
        )
        if summary.excluded_weapon_count:
            status += (
                f" {summary.excluded_weapon_count} Waffen-Kandidat(en) ausgeschlossen "
                "(noch nicht unterstützt, nicht simuliert/veröffentlicht)."
            )
        if summary.excluded_below_min_item_level_count:
            status += (
                f" {summary.excluded_below_min_item_level_count} Kandidat(en) unter "
                f"Itemlevel {summary.min_item_level} ausgeschlossen."
            )
        if summary.excluded_unknown_item_level_count:
            status += (
                f" {summary.excluded_unknown_item_level_count} Kandidat(en) mit "
                "unbekanntem/ungültigem Itemlevel ausgeschlossen."
            )
        if receipt is not None:
            pending_summary = None
            retry_button.configure(state="disabled")
            status += f" Sicher installiert: {receipt.addon_dir}."
            detail = f"Installiert in:\n{receipt.addon_dir}\n\nBackup:\n{receipt.backup}"
        else:
            pending_summary = summary
            retry_button.configure(state="normal")
            if deploy_error is not None:
                status += f" Installation blockiert; Staging bleibt erhalten: {deploy_error}"
                detail = (
                    f"Die Analyse ist sicher gespeichert:\n{summary.results_path}\n\n"
                    f"Installation blockiert:\n{deploy_error}\n\n"
                    "WoW schließen beziehungsweise Ziel korrigieren und "
                    "„Jetzt installieren“ wählen."
                )
            else:
                detail = (
                    "Die geprüfte Results.lua wurde im Staging erzeugt:\n"
                    f"{summary.results_path}\n\n"
                    "Sie kann mit „Jetzt installieren“ sicher übernommen werden."
                )
        status_var.set(status)
        messagebox.showinfo(
            "Analyse abgeschlossen",
            "Nur offensiver DPS-Vergleich; keine defensive Tank- oder Heilermetrik.\n\n" + detail,
            parent=root,
        )

    def finish_error(exc: Exception) -> None:
        nonlocal analysis_running
        analysis_running = False
        analyze_button.configure(state="normal")
        status_var.set(f"Fehler: {exc}")
        messagebox.showerror("Analyse fehlgeschlagen", str(exc), parent=root)

    def analyze() -> None:
        nonlocal analysis_running, pending_summary
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
        if executable.name.casefold() != "simc.exe":
            messagebox.showwarning(
                "Falsche SimulationCraft-Datei",
                "Bitte die Kommandozeilendatei simc.exe auswählen – nicht SimulationCraft.exe.",
                parent=root,
            )
            return
        try:
            settings = SimSettings(
                iterations=iterations_var.get(),
                fight_style=fight_var.get(),
                min_item_level=min_item_level_var.get(),
            )
        except (ValueError, tk.TclError) as exc:
            messagebox.showwarning("Ungültige Einstellungen", str(exc), parent=root)
            return
        analysis_running = True
        pending_summary = None
        analyze_button.configure(state="disabled")
        retry_button.configure(state="disabled")
        status_var.set("Simulation läuft …")
        install_requested = auto_install_var.get()
        addon_target = Path(addon_var.get().strip()) if addon_var.get().strip() else None

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
                if not install_requested:
                    result_queue.put(("success", summary))
                elif addon_target is None:
                    result_queue.put(
                        (
                            "pending",
                            (summary, DeployError("Kein eindeutiges Addon-Verzeichnis ausgewählt")),
                        )
                    )
                else:
                    try:
                        receipt = deploy_completed_analysis(summary, addon_target)
                    except Exception as exc:
                        result_queue.put(("pending", (summary, exc)))
                    else:
                        result_queue.put(("installed", (summary, receipt)))

        threading.Thread(target=worker, daemon=False, name="simc-analysis").start()

    def retry_install() -> None:
        nonlocal analysis_running
        summary = pending_summary
        target_text = addon_var.get().strip()
        if summary is None:
            return
        if not target_text:
            messagebox.showwarning(
                "Addon-Verzeichnis fehlt",
                "Bitte zuerst den installierten LocalGearAdvisor-Addonordner auswählen.",
                parent=root,
            )
            return
        analysis_running = True
        analyze_button.configure(state="disabled")
        retry_button.configure(state="disabled")
        status_var.set("Geprüftes Staging-Ergebnis wird installiert …")
        target = Path(target_text)

        def worker() -> None:
            try:
                receipt = deploy_completed_analysis(summary, target)
            except Exception as exc:
                result_queue.put(("pending", (summary, exc)))
            else:
                result_queue.put(("installed", (summary, receipt)))

        threading.Thread(target=worker, daemon=False, name="results-install").start()

    def poll_results() -> None:
        try:
            kind, payload = result_queue.get_nowait()
        except queue.Empty:
            root.after(100, poll_results)
            return
        if kind == "success" and isinstance(payload, AnalysisSummary):
            finish_success(payload)
        elif kind == "installed" and isinstance(payload, tuple) and len(payload) == 2:
            summary, receipt = payload
            if isinstance(summary, AnalysisSummary) and isinstance(receipt, DeployReceipt):
                finish_success(summary, receipt=receipt)
            else:
                finish_error(RuntimeError("Ungültiges Installationsergebnis"))
        elif kind == "pending" and isinstance(payload, tuple) and len(payload) == 2:
            summary, exc = payload
            if isinstance(summary, AnalysisSummary) and isinstance(exc, Exception):
                finish_success(summary, deploy_error=exc)
            else:
                finish_error(RuntimeError("Ungültiges blockiertes Installationsergebnis"))
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
    retry_button.configure(command=retry_install)
    root.protocol("WM_DELETE_WINDOW", request_close)
    root.after(100, poll_results)
    root.mainloop()
