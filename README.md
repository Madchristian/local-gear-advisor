# Local Gear Advisor

Repository: https://github.com/Madchristian/local-gear-advisor

Lokaler SimulationCraft-gestützter Gegenstandsvergleich für WoW Retail. Der MVP liest einen vollständigen `/simc`-Export einschließlich Taschengegenständen, erzeugt direkte `profileset`-Varianten, startet `simc.exe`, prüft den JSON2-Bericht und erzeugt eine `Results.lua` für ein schlankes Tooltip-Addon.

## Aktueller MVP

- Schutz-Paladin und Elementar-Schamane sowie die übrigen Paladin-/Schamanen-Specs im Ergebnisformat
- Tooltip-Addon gezielt für WoW Retail 12.0.7 und das offizielle SimulationCraft-Addon 12.0.7-02
- Ringe und Schmuckstücke werden gegen beide Plätze getestet
- andere Taschengegenstände gegen ihren jeweiligen Slot; Waffenkandidaten werden im MVP fail-closed abgelehnt
- echte SimC-DPS-Vergleiche einschließlich von SimC modellierter Procs, Spezialeffekte, Talente und Setboni
- exakte Kandidatenidentität über die vom offiziellen SimulationCraft-Addon erzeugten Itemoptionen
- Gültigkeitsprüfung im Spiel gegen Charakter, Realm, Region, Stufe, Volk, Spec, Talentstring, Omnium-Talente und alle relevanten Ausrüstungsslots
- Ergebnisse zeigen Szenario, SimC-Version und Alter; nach sieben Tagen werden sie als veraltet behandelt
- fail-closed bei Secret Values, nicht lesbarem Zustand oder geändertem Baseline-Profil
- `Results.lua` wird erst nach vollständigem, geprüftem JSON2-Bericht atomar veröffentlicht
- keine Cloud, keine Telemetrie und kein Raidbots-Upload

## Noch bewusst nicht enthalten

- vollständige Top-Gear-Kombinatorik mehrerer gleichzeitiger Upgrades
- belastbare defensive Tankmetrik; der MVP bewertet DPS
- automatischer Live-Datenaustausch während WoW läuft
- automatische Addon-Installation oder Änderung von WoW-Dateien
- Bewertung von Gegenständen, die nicht im importierten Taschenbereich standen
- sichere Erkennung jedes still fehlenden SimC-Effektmodells: explizite SimC-Warnungen werden blockiert, aber ein von SimC ohne Warnung ignorierter Spezialeffekt ist im MVP noch nicht automatisch nachweisbar

## Voraussetzungen

1. Offizielles SimulationCraft-WoW-Addon `12.0.7-02` für den `/simc`-Export. Andere Serializer-Versionen werden nicht als kompatibel behauptet.
2. Windows-Version von SimulationCraft für WoW 12.0.7 mit `simc.exe`.
3. Python 3.11+; für die Entwicklung wird `uv` verwendet.

## Entwicklung

```text
uv sync --group dev
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check src tests
```

## Installation als Python-Paket

Beim Arbeiten aus dem Repository liegt das Staging-Addon unter `addon/LocalGearAdvisor`.
Das Wheel enthält zusätzlich die geprüften Addon-Dateien. Bei einer normalen Wheel-Installation
werden erfolgreiche Ergebnisse und Addon-Stagingdateien unter folgendem Benutzerpfad erzeugt:

```text
%LOCALAPPDATA%\LocalGearAdvisor\addon\LocalGearAdvisor
```

Auch dort erfolgt keine automatische Kopie in die WoW-Installation.

## GUI

Nach der Einrichtung kann die Oberfläche direkt per Doppelklick gestartet werden:

```text
Start-LocalGearAdvisor.cmd
```

Alternativ:

```text
.venv\Scripts\local-gear-advisor.exe gui
```

Unter Git Bash:

```text
.venv/Scripts/local-gear-advisor.exe gui
```

In der GUI:

1. `simc.exe` auswählen.
2. In WoW `/simc` ausführen; nicht `nobags` verwenden.
3. Den gesamten Export einfügen oder aus einer UTF-8-Datei laden.
4. `Patchwerk` für Single Target oder `DungeonSlice` als experimentelles M+-Szenario auswählen.
5. „Lokal analysieren“ drücken.

Das Ergebnis wird ausschließlich im jeweiligen Staging-Verzeichnis erzeugt. Im Repository ist das:

```text
addon/LocalGearAdvisor/Results.lua
```

Es erfolgt keine automatische Installation in den WoW-Ordner.

## CLI

```text
.venv/Scripts/local-gear-advisor.exe analyze \
  --input character.simc \
  --simc "C:/SimulationCraft/simc.exe" \
  --iterations 1000 \
  --fight-style Patchwerk
```

## Sicherheitsmodell

- Die eingelesene SimC-Baseline wird aus einer engen Allowlist rekonstruiert. Output-, Datei-, Include-, Import- und Netzwerkdirektiven werden abgelehnt.
- Nicht lesbare Taschenzeilen, unvollständige Baseline-Ausrüstung und Waffenkandidaten blockieren den gesamten Lauf; alte `Results.lua`-Daten bleiben unverändert.
- Subprozesse verwenden eine Argumentliste mit `shell=False`.
- Ein SimC-Fehler, Timeout, Warn-/Fehlerlog, fehlende Provenienz, abweichendes Szenario, falsche DBC-/WoW-Version, abweichende Iterationszahl, fehlender JSON2-Bericht oder unvollständiges Profileset-Ergebnis blockiert die Veröffentlichung.
- CLI und GUI dürfen ausschließlich die festgelegte lokale Stagingdatei `addon/LocalGearAdvisor/Results.lua` schreiben. Direkte WoW-/SavedVariables-Ausgabepfade werden nicht akzeptiert.
- Das Projekt beendet WoW niemals selbst und installiert das Addon nicht automatisch.
- Forschungspakete, Runs, Logs und echte Charakterexporte liegen unter ignorierten Verzeichnissen und gehören nicht in Git.

## Grenzen der Aussage

Ein Tooltipwert ist ein Vergleich mit der simulierten Baseline und dem gewählten Szenario, keine universelle BiS-Aussage. Nicht von SimC modellierte Effekte dürfen nicht als Wert 0 interpretiert werden. Vor einer In-Game-Installation sind ein unabhängiger Review und die ausdrückliche Freigabe erforderlich.
