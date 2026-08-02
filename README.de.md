# Local Gear Advisor

Repository: https://github.com/Madchristian/local-gear-advisor

*[English](README.md)*

Lokaler SimulationCraft-gestützter Gegenstandsvergleich für WoW Retail. Der MVP liest einen
vollständigen `/simc`-Export einschließlich Taschengegenständen, erzeugt direkte
`profileset`-Varianten, startet `simc.exe`, prüft den JSON2-Bericht und führt die Ergebnisse aller
analysierten Charakter-/Spec-Profile in einer gemeinsamen `Results.lua` zusammen.

Ergebnisse gelangen entweder über eine einmalige, geprüfte Addon-Installation ins Spiel, oder
— für jede Analyse danach — indem ein kleiner integritätsgeprüfter Transportblock in den Import-Tab des
Addons eingefügt wird, während WoW einfach weiterläuft. Siehe
[In-Game-Workflow](#in-game-workflow) unten.

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
- der ältere Results-only-Dateipublisher prüft WoW unmittelbar vor jeder Mutation und verweigert `running` oder `unknown`; weil eine Prozessprüfung einen direkt folgenden manuellen WoW-Start nicht verhindern kann, muss WoW während des gesamten Vorgangs geschlossen bleiben
- **neu:** ein In-Game-Import-Tab übernimmt einen integritätsgeprüften Transportblock und aktiviert ihn sofort — ohne Reload und ohne jeden Dateischreibzugriff auf den laufenden WoW-Baum; siehe [In-Game-Workflow](#in-game-workflow)
- keine Cloud, keine Telemetrie und kein Raidbots-Upload

## In-Game-Workflow

Sobald der Addon-Code einmalig geprüft installiert wurde (siehe
[Installation als Python-Paket](#installation-als-python-paket)), lässt sich jede weitere
Analyse durchführen, **ohne WoW dafür je wieder zu schließen**. Nichts hier schreibt in den
laufenden WoW-Baum; das Addon ändert ausschließlich seine eigenen SavedVariables, im Speicher,
in der laufenden Sitzung.

1. **Export, in WoW.** Local Gear Advisor öffnen (`/lga`, der Minimap-Button oder das
   Blizzard-Addon-Compartment-Symbol), zum Tab **Analyse** wechseln und „Export erzeugen“
   klicken. Das ruft die vom offiziellen SimulationCraft-Addon dokumentierte Methode
   `SimulationcraftAPI:GetSimcProfile(false, false, false, nil)` direkt auf und zeigt den
   Text bereits markiert und fokussiert an. WoW-Addons können nicht auf die
   Windows-Zwischenablage schreiben — deshalb selbst mit **Strg+C** kopieren; es wird keine
   „kopiert“-Behauptung vorgetäuscht, der man vertrauen müsste.
2. **Analysieren, auf dem Desktop.** Diesen Export mit Strg+V in das Export-Feld des
   Windows-Helfers einfügen und „Lokal analysieren“ klicken. Das läuft exakt dieselbe lokale
   SimC-Pipeline wie bisher (siehe [CLI](#cli)/[GUI](#gui)) und füllt bei Erfolg ein zweites,
   nur lesbares Feld „Importtext für /lga im Spiel“ mit einem kleinen integritätsgeprüften
   Transportblock. „Importtext kopieren“ legt ihn in die Windows-Zwischenablage — der
   Desktop-Helfer *darf* auf die echte Zwischenablage zugreifen.
3. **Prüfen, in WoW.** Zurück zu WoW wechseln (läuft weiterhin), den Tab **Import** öffnen,
   den Transporttext mit Strg+V einfügen und „Prüfen“ klicken. Das decodiert und validiert den
   Block ausschließlich gegen dasselbe semantische Schema, das auch `Results.lua`-Einträge
   erfüllen müssen — es mutiert dabei nie SavedVariables.
4. **Importieren.** „Importieren“ klicken. Das ist der einzige Punkt, an dem tatsächlich etwas
   geschrieben wird: Das geprüfte Profil wird sofort aktiv (kein `/reload`, kein Ausloggen).
   „Importieren“ ist nur für exakt den zuletzt geprüften Text aktiv — jede Änderung am Text
   invalidiert das sofort wieder und verlangt eine erneute Prüfung.
5. **Profile.** Der Tab **Profile** listet jeden lokal bekannten Charakter/Spec, sowohl
   importierte als auch aus der gestagten Ergebnisdatei, mit Szenario, Itemanzahl, Alter und
   Quelle. Importierte Profile lassen sich löschen (ein zweiter, bestätigender Klick); die
   letzte Änderung (Import oder Löschen) lässt sich mit einem Klick rückgängig machen, solange
   seitdem nichts anderes an diesem Identitätseintrag verändert hat.

Importierte Profile und die einstufige Undo-Momentaufnahme sind accountweite SavedVariables.
Apply wirkt sofort im Speicher. WoW schreibt diese Daten normalerweise beim Ausloggen oder bei
`/reload` auf die Festplatte; ein Client- oder Betriebssystemabsturz vor diesem Flush kann den
letzten Import verlieren. Für die sofortige Nutzung ist kein Reload nötig, nach einem wichtigen
Import ist ein einmaliges `/reload` für zeitnahe dauerhafte Speicherung aber empfehlenswert.
Beim Löschen eines importierten Overrides kann das ältere eingebettete `Results.lua`-Fallback
wieder sichtbar werden; die Oberfläche meldet diesen Übergang ausdrücklich.

Das schließt genau die Lücke, die der ursprüngliche MVP offenließ: Bisher musste für ein neues
Ergebnis vor dem Tooltip WoW geschlossen werden, damit der Desktop-Helfer `Results.lua` in den
laufenden `AddOns`-Ordner schreiben konnte, und WoW musste danach neu gestartet werden. Dieser
Dateischreibzugriff passiert jetzt nur noch für die einmalige Installation des Addon-*Codes*;
jede routinemäßige Neuanalyse danach bleibt vollständig innerhalb der laufenden Sitzung.

## Noch bewusst nicht enthalten

- vollständige Top-Gear-Kombinatorik mehrerer gleichzeitiger Upgrades
- belastbare defensive Tankmetrik; der MVP bewertet DPS
- belastbare Heilermetrik; auch für Heiler ist das Ergebnis ausschließlich ein offensiver DPS-Vergleich
- Live-Datenaustausch während WoW läuft, außer über den oben beschriebenen integritätsgeprüften In-Game-Import-Transport; dateibasierter Austausch verweigert einen laufenden oder unbekannten Preflight, kann einen unmittelbar danach erfolgenden manuellen WoW-Start aber nicht atomar verhindern
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

Auch beim Arbeiten aus dem Repository werden erfolgreiche Ergebnisse und Addon-Stagingdateien
außerhalb des Source-Checkouts unter folgendem Benutzerpfad erzeugt. Das Wheel enthält zusätzlich
die geprüften Addon-Dateien:

```text
%LOCALAPPDATA%\LocalGearAdvisor\addon\LocalGearAdvisor
```

Ein leerer, nur aus Leerzeichen bestehender oder relativer `LOCALAPPDATA`-Wert fällt auf den
absoluten Pfad `%USERPROFILE%\AppData\Local` zurück. Die Source-`Results.lua` wird selbst als
explizites Analyseziel abgelehnt. Das Staging bleibt die Quelle. Die ausdrücklich aktivierte GUI-/CLI-Liveoption
veröffentlicht ausschließlich `Results.lua` und verlangt, dass die installierten Code-Dateien
bereits bytegenau zu dieser Version passen; sie ist bewusst **kein** Code-Updater.

Eine vollständige, bytegenau zurückgelesene Quelle für die manuelle Installation wird aus der
Repository-Umgebung oder einem installierten Wheel so erzeugt:

```text
local-gear-advisor stage-addon --output C:\Temp\LocalGearAdvisor-Staging
```

Der Zielpfad darf noch nicht existieren. Der Befehl schreibt ausschließlich dorthin, enthält
alle sieben Codedateien plus die leere Schema-2-`Results.lua` und schreibt niemals in WoW.
Schlägt das Staging fehl, bleibt sein zufällig benanntes verstecktes Geschwisterverzeichnis
absichtlich zur Prüfung erhalten, statt pfadbasiert gelöscht zu werden; so kann keine parallel
ersetzte Verzeichnisgeneration gelöscht werden. Schlägt der Readback nach der Veröffentlichung
fehl, bleibt auch das Ziel als Quarantäne erhalten und der Befehl meldet einen Fehler. Nur ein
erfolgreicher Lauf hinterlässt kein privates Stagingverzeichnis.

Für das einmalige Programmupdate muss WoW nachweislich geschlossen sein. Danach werden
`LocalGearAdvisor.toc`, `Localization.lua`, `Sha256.lua`, `Core.lua`, `Import.lua`,
`Minimap.lua` und `UI.lua` aus dem geprüften Staging in den Addon-Ordner übernommen. Bei einem
Update bleibt die vorhandene `Results.lua` erhalten; vor dem Austausch wird der komplette
Addon-Ordner extern gesichert. Bei einer Erstinstallation ohne vorhandenes Addon wird der ganze
Staging-Ordner einschließlich der leeren Schema-2-`Results.lua` kopiert. Dateien unter `WTF`
werden dabei nie verändert. Nach diesem einmaligen Code-Install kann jede weitere Analyse den
[In-Game-Import-Workflow](#in-game-workflow) nutzen — WoW muss dafür nicht mehr geschlossen
werden.
WoW muss geschlossen bleiben, bis Kopie und Hash-Readback vollständig beendet sind: Keine
Userspace-Prozessabfrage kann einen späteren manuellen Start von `Wow.exe` atomar sperren.

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

1. Die Kommandozeilendatei `simc.exe` auswählen; `SimulationCraft.exe` wird abgelehnt. Falls
   SimulationCraft noch fehlt, öffnet „SimulationCraft herunterladen…“ ausschließlich die feste
   offizielle HTTPS-Downloadseite `https://www.simulationcraft.org/download.html` im Standardbrowser.
   Der Helper lädt oder startet selbst keinen Installer.
2. Den installierten `Interface/AddOns/LocalGearAdvisor`-Ordner auswählen. Bei genau einem eindeutigen Standardfund wird er nur lesend vorausgewählt.
3. In WoW `/simc` ausführen (oder den addon-eigenen Analyse-Tab nutzen, siehe [In-Game-Workflow](#in-game-workflow)); nicht `nobags` verwenden.
4. Den gesamten Export einfügen oder aus einer UTF-8-Datei laden.
5. `Patchwerk` für Single Target oder `DungeonSlice` als experimentelles M+-Szenario auswählen.
6. Mindest-Itemlevel festlegen (`282` ist Standard, `0` deaktiviert den Filter).
7. „Lokal analysieren“ drücken.

Das gemeinsame Ergebnis und sein kanonischer JSON-Zustand werden außerhalb des Repositories erzeugt:

```text
%LOCALAPPDATA%\LocalGearAdvisor\addon\LocalGearAdvisor\Results.lua
%LOCALAPPDATA%\LocalGearAdvisor\state\profiles.json
```

Nach Abschluss der Analyse füllt sich ein nur lesbares Feld „Importtext für /lga im Spiel“ mit
einem integritätsgeprüften Transportblock; „Importtext kopieren“ legt ihn in die Windows-Zwischenablage,
sodass er in WoWs Import-Tab eingefügt werden kann (siehe
[In-Game-Workflow](#in-game-workflow)) — dafür ist keine Dateiinstallation nötig, und WoW kann
dabei weiterlaufen.

Ist die Auto-Installation aktiviert, wird danach ausschließlich `Results.lua` übernommen. Läuft WoW oder ist sein Zustand unbekannt, bleibt das Staging erhalten. Nach dem Schließen von WoW kann „Jetzt installieren“ dieselbe validierte SHA-256-Datei übernehmen, ohne SimC erneut zu starten. `Core.lua`, die TOC und SavedVariables werden dabei nie überschrieben; sie werden auf Kompatibilität beziehungsweise Unverändertheit geprüft.

## Addon im Spiel

- **Slash-Befehl:** `/lga` blendet das Fenster ein/aus.
- **Minimap-Button:** frei am Ring verschiebbar; kann über Einstellungen ein-/ausgeblendet
  werden, wobei sowohl Winkel als auch Sichtbarkeit sitzungsübergreifend in
  `LocalGearAdvisorSettings` gespeichert bleiben. Auch das Blizzard-Addon-Compartment-Symbol
  blendet das Fenster ein/aus, defensiv abgesichert, damit eine künftige API-Änderung dort nie
  zu einem unbehandelten Lua-Fehler werden kann.
- **Analyse-Tab:** erzeugt den `/simc`-Export direkt über das offizielle
  SimulationCraft-Addon und zeigt ihn markiert für den manuellen Strg+C-Kopiervorgang (siehe
  Schritt 1 im [In-Game-Workflow](#in-game-workflow)).
- **Import-Tab:** den Transporttext des Windows-Helfers einfügen, mit „Prüfen“ validieren
  (ohne Mutation) und danach „Importieren“ (der einzige Punkt, an dem SavedVariables
  geschrieben werden). Jede Textänderung nach einer Prüfung deaktiviert „Importieren“ sofort
  wieder, bis erneut geprüft wurde.
- **Profile-Tab:** listet jedes lokal bekannte Charakter-/Spec-Profil, sowohl importierte als
  auch aus der gestagten Ergebnisdatei, mit Szenario, Itemanzahl, Alter und Quelle; importierte
  Profile lassen sich löschen (zweiter Klick bestätigt), und der letzte Import/Löschvorgang
  lässt sich rückgängig machen.
- **Einstellungen-Tab:** Fenstergrößen-Voreinstellungen, Zurücksetzen der Fensterposition und
  Sichtbarkeit des Minimap-Buttons — alles gespeichert.
- **Lokalisierung:** alle sichtbaren Texte liegen in einer einzigen Datei
  (`Localization.lua`); `deDE` ist vollständig übersetzt, jede andere Locale fällt auf `enUS`
  zurück, es gibt keine teilweise/gemischte Locale-Tabelle.
- **Tooltip:** der Vergleichswert eines Gegenstands wird ausschließlich bei einer *exakten*
  Varianten-Übereinstimmung angezeigt — gleiche Itemoptionen (Verzauberung/Sockel/Bonus-IDs/
  Crafted-Stats), gleicher Charakter/Spec/Level/Volk, gleicher Talent- und
  Omnium-Talent-String, gleiche angelegte Baseline-Ausrüstung, gleicher WoW-/SimC-Build und
  nicht älter als sieben Tage. Alles andere schlägt still fehl oder zeigt einen expliziten
  Veraltet-/Unbekannt-Grund; ein Gegenstand wird nie als DPS-Änderung von 0 bewertet, nur weil
  SimC ihn nicht modelliert hat.

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
  --addon-dir "C:/Games/World of Warcraft/_retail_/Interface/AddOns/LocalGearAdvisor"
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

Die nachvollziehbare MVP-Abnahmematrix steht in [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md). Sie trennt automatisierte Nachweise ausdrücklich von der abgeschlossenen persönlichen `/simc`- und Retail-In-Game-Abnahme.

## Sicherheitsmodell

- Die eingelesene SimC-Baseline wird aus einer engen Allowlist rekonstruiert. Doppelte Direktiven, ungültige gebundene Metadaten sowie Output-, Datei-, Include-, Import- und Netzwerkdirektiven werden abgelehnt.
- Nicht lesbare Taschenzeilen, unvollständige Baseline-Ausrüstung und die nur per Tooltip vollständig serialisierbaren Titan-Disc-Gürtel blockieren den gesamten Lauf; alte `Results.lua`-Daten bleiben unverändert.
- Bei aktiviertem Filter werden Kandidaten unterhalb des gewählten Mindest-Itemlevels oder mit unbekanntem Itemlevel zuerst nach Fingerprint dedupliziert und ausgeschlossen. Verbleibende Waffen-Slots werden anschließend als nicht unterstützt gemeldet. Keine dieser Kategorien wird simuliert oder in `Results.lua` veröffentlicht.
- Subprozesse verwenden eine Argumentliste mit `shell=False`.
- Ein SimC-Fehler, Timeout, Warn-/Fehlerlog, fehlende Provenienz, abweichendes Szenario, falsche DBC-/WoW-Version, abweichende Iterationszahl, fehlender JSON2-Bericht oder unvollständiges Profileset-Ergebnis blockiert die Veröffentlichung.
- Ein fehlendes, strukturell ungültiges oder nicht zur gemeldeten SimC-Git-Revision passendes Spezialisierungsregister blockiert die Veröffentlichung. Die Build-/CI-Prüfung stellt zusätzlich sicher, dass das eingecheckte Register bytegenau aus dem gepinnten Quell-Snapshot reproduzierbar ist. Unbekannte Klassen-/Spec-Paare bleiben fail-closed.
- Analyse und Migration veröffentlichen ausschließlich in die festgelegte lokale Stagingdatei. Die optionale Result-only-Installation akzeptiert nur einen normalen, nicht umgeleiteten `Interface/AddOns/LocalGearAdvisor`-Pfad mit exakt kompatiblem `Core.lua` und TOC.
- Der kanonische Mehrprofilzustand und seine Lua-Projektion werden unter einem gemeinsamen OS-Lock veröffentlicht. Ein pfadgebundenes Journal bindet alte und neue Hashgenerationen, restauriert kontrollierte Fehler sofort und repariert nach einem Prozessabbruch nur bekannte Zwischenzustände; eine fremde Generation wird fail-closed erhalten.
- Vor der Result-only-Veröffentlichung werden Zielinventar, Staging-Hash und die bytegenaue Projektion aus dem streng validierten kanonischen JSON-State geprüft. Ein an den kanonischen Zielpfad statt an den frei wählbaren Receipt-Pfad gebundener OS-Lock serialisiert alle kooperierenden Publisher für dieselbe `Results.lua`. Gesperrte Verzeichnisidentitäten sowie write-/replace-gesperrte Handles auf `Core.lua` und TOC verhindern einen inkompatiblen Codeaustausch während Recovery und Veröffentlichung. Frische WoW-Prüfungen laufen unmittelbar vor jedem vorbereitenden Live-Tree-Write, jedem Recovery-Link, Rename, Publish und jeder kontrollierten Bereinigung; `running` und `unknown` verweigern die jeweilige Mutation. Das ist eine Preflight-Zusage, keine atomare Prozessstartsperre: Der Bediener muss WoW während des gesamten Vorgangs geschlossen halten. Die alte Generation wird atomar in ein eindeutiges Backup außerhalb von `AddOns` verschoben; die neue Generation wird ausschließlich per Create-if-absent veröffentlicht und anschließend gelesen und gehasht. Ein persistentes Journal repariert einen Prozessabbruch zwischen diesen Schritten. Eine konkurrierende fremde Generation wird niemals überschrieben. Nach einer bereits verifizierten Veröffentlichung wird bei einem späteren Receipt-, SavedVariables- oder Prozessfehler kein automatischer Rollback mehr versucht; die neue Generation und das Backup bleiben zur sicheren Prüfung erhalten. Receipt und Pending-Journal liegen vollständig außerhalb des WoW-Retail-Baums; der zielgebundene Publisher-Lock liegt im normalen Benutzer-Temp-Verzeichnis und wird zusätzlich gegen den Retail-Baum geprüft. Das Receipt speichert für SavedVariables nur Anzahl und Gesamtdigest, keine persönlichen Pfade. Schema-2-DPS-Werte sind auf `0..10^12` und Delta-Prozentwerte auf `±10^6` begrenzt; darüber liegende Daten werden in Python und Lua fail-closed verworfen.
- **In-Game-Import-Transport (neu):** Der Transportblock ist eine kleine, selbst entworfene kanonische Grammatik (niemals Lua-Quellcode), byteweise mit harten Grenzen tokenisiert — maximal 256 KiB insgesamt, maximale Verschachtelungstiefe 8, maximal 20.000 Einträge pro Container, maximal 1.000.000 Bytes pro Zeichenkette, streng aufsteigende eindeutige Dict-Schlüssel, keine NaN-/Inf-artigen Token, keine Ganzzahlen mit führender Null. Er trägt eine eigene SHA-256-Prüfsumme (eine reine Lua-Implementierung, da WoWs Lua 5.1 kein `bit32`/keine Bitlib besitzt, gegen Pythons `hashlib` für viele Eingaben einschließlich der echten Nutzdaten gegengeprüft). Import.lua **ruft niemals `load`/`loadstring` oder irgendeine Form von `eval` auf**; ein bösartig eingefügter Text ist immer inerte Daten, niemals ausführbarer Code, und ein decodiertes Profil wird vor der Anwendung gegen dasselbe semantische Schema geprüft, das auch `Results.lua`-Einträge bereits erfüllen müssen.
- **Transaktionales SavedVariables-Apply (neu):** `LocalGearAdvisorDB` wird ausschließlich von einer einzigen Funktion beschrieben, die zunächst vollständig validiert und erst bei Erfolg mutiert — ein Form- oder semantischer Fehler lässt die bestehende Datenbank bytegenau unverändert. Apply/Delete ersetzen oder entfernen jeweils nur die exakt passende Identität (Region/Realm/Charakter/Spec-ID); jeder andere Eintrag bleibt exakt erhalten. Eine einstufige Undo-Momentaufnahme (`LocalGearAdvisorUndo`, eine separate SavedVariable) speichert Identität sowie das Profil vor/nach der Änderung und verweigert die Rückgängigmachung, falls diese Identität seither durch einen neueren Import oder eine andere Änderung berührt wurde — Undo kann also nie stillschweigend einen unabhängigen, neueren Zustand überschreiben. Undo ist einmalig: Bei Erfolg löscht es seine eigene Momentaufnahme.
- Das Projekt beendet WoW niemals selbst. `running` und `unknown` blockieren fail-closed.
- Forschungspakete, Runs, Logs und echte Charakterexporte liegen unter ignorierten Verzeichnissen und gehören nicht in Git.

## Grenzen der Aussage

Ein Tooltipwert ist ein Vergleich mit der simulierten Baseline und dem gewählten Szenario, keine universelle BiS-Aussage. Nicht von SimC modellierte Effekte dürfen nicht als Wert 0 interpretiert werden. Vor einer In-Game-Installation sind ein unabhängiger Review und die ausdrückliche Freigabe erforderlich.

## Lizenz

Copyright (c) 2026 Christian. Alle Rechte vorbehalten. Private, nicht kommerzielle Nutzung,
persönliche Sicherungskopien und unveränderte Weitergabe innerhalb einer privaten Gilde oder
Spielgemeinschaft sind erlaubt. Änderungen, Reuploads, Spiegelungen, Aufnahme in Pakete und
kommerzielle Nutzung benötigen vorherige schriftliche Genehmigung. Die vollständigen verbindlichen
Bedingungen stehen in [`LICENSE.txt`](LICENSE.txt).
