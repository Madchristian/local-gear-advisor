# Local Gear Advisor

Repository: https://github.com/Madchristian/local-gear-advisor

Lokaler SimulationCraft-gestützter Gegenstandsvergleich für WoW Retail. Der MVP liest einen vollständigen `/simc`-Export einschließlich Taschengegenständen, erzeugt direkte `profileset`-Varianten, startet `simc.exe`, prüft den JSON2-Bericht und erzeugt eine `Results.lua` für ein schlankes Tooltip-Addon.

## Aktueller MVP

- alle 40 in der gepinnten SimulationCraft-Revision `5a982a3` enthaltenen Klassen-/Spec-Kombinationen über ein deterministisch erzeugtes Register; darunter Wächter-Druide (`104`) und Verschlinger-Dämonenjäger (`1480`)
- Tooltip-Addon gezielt für WoW Retail 12.0.7 und das offizielle SimulationCraft-Addon 12.1.0-01
- Ringe und Schmuckstücke werden gegen beide Plätze getestet
- konfigurierbarer Mindest-Itemlevel-Filter (GUI/CLI standardmäßig 282); angelegte Baseline-Ausrüstung wird nie gefiltert
- andere Kandidaten gegen ihren jeweiligen Slot; Waffenkandidaten werden transparent ausgeschlossen und nie simuliert oder veröffentlicht
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
- belastbare Heilermetrik; auch für Heiler ist das Ergebnis ausschließlich ein offensiver DPS-Vergleich
- automatischer Live-Datenaustausch während WoW läuft
- automatische Addon-Installation oder Änderung von WoW-Dateien
- Bewertung von Gegenständen, die nicht im importierten Taschenbereich standen
- sichere Erkennung jedes still fehlenden SimC-Effektmodells: explizite SimC-Warnungen werden blockiert, aber ein von SimC ohne Warnung ignorierter Spezialeffekt ist im MVP noch nicht automatisch nachweisbar

## Voraussetzungen

1. Offizielles SimulationCraft-WoW-Addon `12.1.0-01` für den `/simc`-Export. Andere Serializer-Versionen werden nicht als kompatibel behauptet.
2. Windows-Version von SimulationCraft für WoW `12.0.7.68887` mit `simc.exe`; andere DBC-/Buildstände werden fail-closed abgelehnt.
3. Python 3.11+; für die Entwicklung wird `uv` verwendet.

## Entwicklung

```text
uv sync --group dev
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check src tests tools
.venv\Scripts\python.exe tools\generate_spec_registry.py --revision 5a982a3 --source tests\fixtures\sc_specialization_data.inc --check
```

### Spezialisierungsregister aktualisieren

Die Laufzeit verwendet keine KI und rät keine Spec-IDs. Das eingecheckte
`src/local_gear_advisor/data/spec_registry.json` wird aus der öffentlichen, auf eine konkrete
Git-Revision festgelegten SimulationCraft-Datei `sc_specialization_data.inc` erzeugt. Für die
aktuell verwendete Revision kann es ohne Netzwerkzugriff reproduziert und geprüft werden:

```text
.venv\Scripts\python.exe tools\generate_spec_registry.py \
  --revision 5a982a3 \
  --source tests\fixtures\sc_specialization_data.inc \
  --check
```

Beim Wechsel auf eine neue SimC-Revision erzeugt derselbe Befehl ohne `--source` das Register
direkt von der fest an diese Revision gebundenen HTTPS-Quelle. Redirects, übergroße oder
unvollständige Quellen, unbekannte Klassenpräfixe, doppelte IDs und fehlende Klassen werden
fail-closed abgelehnt. Erst nach Review und vollständigen Tests wird das erzeugte Register
eingecheckt. Der JSON2-Bericht muss anschließend exakt dieselbe SimC-Git-Revision melden.

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
5. Mindest-Itemlevel festlegen (`282` ist Standard, `0` deaktiviert den Filter).
6. „Lokal analysieren“ drücken.

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
  --min-item-level 282 \
  --fight-style Patchwerk
```

## Tests und Abnahme

```text
uv run ruff format --check src tests tools
uv run ruff check src tests tools
uv run pytest -q
uv run python tools/generate_spec_registry.py --revision 5a982a3 --source tests/fixtures/sc_specialization_data.inc --check
uv build
```

Die nachvollziehbare MVP-Abnahmematrix steht in [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md). Sie trennt automatisierte Nachweise ausdrücklich von der noch ausstehenden persönlichen `/simc`- und In-Game-Abnahme.

## Sicherheitsmodell

- Die eingelesene SimC-Baseline wird aus einer engen Allowlist rekonstruiert. Doppelte Direktiven, ungültige gebundene Metadaten sowie Output-, Datei-, Include-, Import- und Netzwerkdirektiven werden abgelehnt.
- Nicht lesbare Taschenzeilen, unvollständige Baseline-Ausrüstung und die nur per Tooltip vollständig serialisierbaren Titan-Disc-Gürtel blockieren den gesamten Lauf; alte `Results.lua`-Daten bleiben unverändert.
- Bei aktiviertem Filter werden Kandidaten unterhalb des gewählten Mindest-Itemlevels oder mit unbekanntem Itemlevel zuerst nach Fingerprint dedupliziert und ausgeschlossen. Verbleibende Waffen-Slots werden anschließend als nicht unterstützt gemeldet. Keine dieser Kategorien wird simuliert oder in `Results.lua` veröffentlicht.
- Subprozesse verwenden eine Argumentliste mit `shell=False`.
- Ein SimC-Fehler, Timeout, Warn-/Fehlerlog, fehlende Provenienz, abweichendes Szenario, falsche DBC-/WoW-Version, abweichende Iterationszahl, fehlender JSON2-Bericht oder unvollständiges Profileset-Ergebnis blockiert die Veröffentlichung.
- Ein fehlendes, strukturell ungültiges oder nicht zur gemeldeten SimC-Git-Revision passendes Spezialisierungsregister blockiert die Veröffentlichung. Die Build-/CI-Prüfung stellt zusätzlich sicher, dass das eingecheckte Register bytegenau aus dem gepinnten Quell-Snapshot reproduzierbar ist. Unbekannte Klassen-/Spec-Paare bleiben fail-closed.
- CLI und GUI dürfen ausschließlich die festgelegte lokale Stagingdatei `addon/LocalGearAdvisor/Results.lua` schreiben. Direkte WoW-/SavedVariables-Ausgabepfade werden nicht akzeptiert.
- Das Projekt beendet WoW niemals selbst und installiert das Addon nicht automatisch.
- Forschungspakete, Runs, Logs und echte Charakterexporte liegen unter ignorierten Verzeichnissen und gehören nicht in Git.

## Grenzen der Aussage

Ein Tooltipwert ist ein Vergleich mit der simulierten Baseline und dem gewählten Szenario, keine universelle BiS-Aussage. Nicht von SimC modellierte Effekte dürfen nicht als Wert 0 interpretiert werden. Vor einer In-Game-Installation sind ein unabhängiger Review und die ausdrückliche Freigabe erforderlich.
