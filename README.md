# Local Gear Advisor

Repository: https://github.com/Madchristian/local-gear-advisor

Lokaler SimulationCraft-gestützter Gegenstandsvergleich für WoW Retail. Der MVP liest einen
vollständigen `/simc`-Export einschließlich Taschengegenständen, erzeugt direkte
`profileset`-Varianten, startet `simc.exe`, prüft den JSON2-Bericht und führt die Ergebnisse aller
analysierten Charakter-/Spec-Profile in einer gemeinsamen `Results.lua` zusammen.

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
- Schema 2 hält mehrere Charaktere und mehrere Specs pro Charakter; eine Analyse ersetzt nur die exakt passende Identität aus Region, Realm, Charaktername und numerischer Spec-ID
- das Addon wählt ausschließlich den exakt eingeloggten Charakter und die aktive Spec; bei fehlenden, doppelten oder missgebildeten Profilen wird kein Ergebnis eines anderen Charakters angezeigt
- die GUI kann eine abgeschlossene, hashgebundene Staging-Datei automatisch oder über einen separaten Retry sicher installieren, aber nur bei frisch und eindeutig geschlossenem WoW
- keine Cloud, keine Telemetrie und kein Raidbots-Upload

## Noch bewusst nicht enthalten

- vollständige Top-Gear-Kombinatorik mehrerer gleichzeitiger Upgrades
- belastbare defensive Tankmetrik; der MVP bewertet DPS
- belastbare Heilermetrik; auch für Heiler ist das Ergebnis ausschließlich ein offensiver DPS-Vergleich
- Live-Datenaustausch während WoW läuft; laufendes oder nicht sicher prüfbares WoW blockiert jeden Austausch fail-closed
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

Auch dort bleibt das Staging die Quelle. Eine Live-Installation erfolgt nur über die ausdrücklich
aktivierte GUI-Option oder CLI-Option und ausschließlich nach den Sicherheitsprüfungen.

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

1. Die Kommandozeilendatei `simc.exe` auswählen; `SimulationCraft.exe` wird abgelehnt.
2. Den installierten `Interface/AddOns/LocalGearAdvisor`-Ordner auswählen. Bei genau einem eindeutigen Standardfund wird er nur lesend vorausgewählt.
3. In WoW `/simc` ausführen; nicht `nobags` verwenden.
4. Den gesamten Export einfügen oder aus einer UTF-8-Datei laden.
5. `Patchwerk` für Single Target oder `DungeonSlice` als experimentelles M+-Szenario auswählen.
6. Mindest-Itemlevel festlegen (`282` ist Standard, `0` deaktiviert den Filter).
7. „Lokal analysieren“ drücken.

Das gemeinsame Ergebnis und sein kanonischer JSON-Zustand werden zuerst im Staging erzeugt. Im Repository sind das:

```text
addon/LocalGearAdvisor/Results.lua
state/profiles.json
```

Ist die Auto-Installation aktiviert, wird danach ausschließlich `Results.lua` übernommen. Läuft WoW oder ist sein Zustand unbekannt, bleibt das Staging erhalten. Nach dem Schließen von WoW kann „Jetzt installieren“ dieselbe validierte SHA-256-Datei übernehmen, ohne SimC erneut zu starten. `Core.lua`, die TOC und SavedVariables werden dabei nie überschrieben; sie werden auf Kompatibilität beziehungsweise Unverändertheit geprüft.

## CLI

```text
.venv/Scripts/local-gear-advisor.exe analyze \
  --input character.simc \
  --simc "C:/SimulationCraft/simc.exe" \
  --iterations 1000 \
  --min-item-level 282 \
  --fight-style Patchwerk
```

Die CLI bleibt standardmäßig staging-only. Eine Live-Installation muss ausdrücklich aktiviert und auf den Addonordner begrenzt werden:

```text
.venv/Scripts/local-gear-advisor.exe analyze \
  --input character.simc \
  --simc "C:/SimulationCraft/simc.exe" \
  --install-live \
  --addon-dir "D:/World of Warcraft/_retail_/Interface/AddOns/LocalGearAdvisor"
```

Vorhandene, vom Projektgenerator erzeugte Schema-1-Archive können ohne Lua-Ausführung eng und explizit in den gemeinsamen Schema-2-Zustand migriert werden:

```text
.venv/Scripts/python.exe tools/import_v1_results.py archive-a/Results.lua archive-b/Results.lua
```

Der Migrationsparser akzeptiert nur eine einzelne literale `LocalGearAdvisorResults`-Zuweisung mit dem exakten alten Feldschema; Lua-Aufrufe, Zusatzfelder, doppelte Schlüssel und andere Strukturen werden abgelehnt.

## Datenquellen und Armory-Grenzen

Battle.net Armory kann künftig optional eine Charakterliste, öffentliche Profildaten und angelegte Ausrüstung liefern. Sie enthält jedoch nicht zuverlässig Taschen, Charakterbank, Reagenzbank, Kriegsmeutenbank oder alle lokalen Itemvarianten. Sie ist daher kein Ersatz für einen vollständigen lokalen `/simc`-Export. Eine spätere Armory-Integration bleibt opt-in und benötigt vor Umsetzung einen festgelegten OAuth-, Datenschutz-, Region-/Realm-, Rate-Limit-, Cache- und Fail-Closed-Vertrag. Für vollständige Kandidatendaten bleibt `/simc` Standard; langfristig kann ein accountweiter lokaler Addon-Sammler bereits geladene Ausrüstung, Taschen und Bankbereiche in SavedVariables erfassen.

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
- Analyse und Migration veröffentlichen ausschließlich in die festgelegte lokale Stagingdatei. Die optionale Result-only-Installation akzeptiert nur einen normalen, nicht umgeleiteten `Interface/AddOns/LocalGearAdvisor`-Pfad mit exakt kompatiblem `Core.lua` und TOC.
- Der kanonische Mehrprofilzustand und seine Lua-Projektion werden unter einem gemeinsamen OS-Lock veröffentlicht. Ein pfadgebundenes Journal bindet alte und neue Hashgenerationen, restauriert kontrollierte Fehler sofort und repariert nach einem Prozessabbruch nur bekannte Zwischenzustände; eine fremde Generation wird fail-closed erhalten.
- Vor der Result-only-Veröffentlichung werden Zielinventar, Staging-Hash und die bytegenaue Projektion aus dem streng validierten kanonischen JSON-State geprüft. Ein an den kanonischen Zielpfad statt an den frei wählbaren Receipt-Pfad gebundener OS-Lock serialisiert alle kooperierenden Publisher für dieselbe `Results.lua`. Gesperrte Verzeichnisidentitäten sowie write-/replace-gesperrte Handles auf `Core.lua` und TOC verhindern einen inkompatiblen Codeaustausch während Recovery und Veröffentlichung. Frische WoW-Prüfungen unmittelbar vor jedem vorbereitenden Live-Tree-Write, jedem Recovery-Link, Rename, Publish und jeder kontrollierten Bereinigung schützen den Vorgang. Die alte Generation wird atomar in ein eindeutiges Backup außerhalb von `AddOns` verschoben; die neue Generation wird ausschließlich per Create-if-absent veröffentlicht und anschließend gelesen und gehasht. Ein persistentes Journal repariert einen Prozessabbruch zwischen diesen Schritten. Eine konkurrierende fremde Generation wird niemals überschrieben. Nach einer bereits verifizierten Veröffentlichung wird bei einem späteren Receipt-, SavedVariables- oder Prozessfehler kein automatischer Rollback mehr versucht; die neue Generation und das Backup bleiben zur sicheren Prüfung erhalten. Receipt und Pending-Journal liegen vollständig außerhalb des WoW-Retail-Baums; der zielgebundene Publisher-Lock liegt im normalen Benutzer-Temp-Verzeichnis und wird zusätzlich gegen den Retail-Baum geprüft. Das Receipt speichert für SavedVariables nur Anzahl und Gesamtdigest, keine persönlichen Pfade. Schema-2-DPS-Werte sind auf `0..10^12` und Delta-Prozentwerte auf `±10^6` begrenzt; darüber liegende Daten werden in Python und Lua fail-closed verworfen.
- Das Projekt beendet WoW niemals selbst. `running` und `unknown` blockieren fail-closed.
- Forschungspakete, Runs, Logs und echte Charakterexporte liegen unter ignorierten Verzeichnissen und gehören nicht in Git.

## Grenzen der Aussage

Ein Tooltipwert ist ein Vergleich mit der simulierten Baseline und dem gewählten Szenario, keine universelle BiS-Aussage. Nicht von SimC modellierte Effekte dürfen nicht als Wert 0 interpretiert werden. Vor einer In-Game-Installation sind ein unabhängiger Review und die ausdrückliche Freigabe erforderlich.
