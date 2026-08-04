LOCAL GEAR ADVISOR – PORTABLER WINDOWS-HELPER 0.2.1
==================================================

Kompatibilität
- Windows 10/11, 64 Bit
- Local Gear Advisor WoW-Addon 0.2.0 (Transportformat LGA2)
- World of Warcraft Retail

Start
1. ZIP vollständig in einen normalen Ordner entpacken.
2. LocalGearAdvisor.exe starten. Python und Administratorrechte sind nicht erforderlich.
3. Eine offizielle lokale simc.exe auswählen. SimulationCraft ist aus Lizenz-,
   Provenienz- und Aktualisierungsgründen nicht enthalten.
4. In WoW mit dem SimulationCraft-Addon einen vollständigen /simc-Export erzeugen.
5. Export im Helper einfügen und lokal analysieren.
6. „Importtext kopieren“ anklicken und den Text im Import-Reiter des WoW-Addons einfügen.

Sicherheit und Datenschutz
- Charakter-, Inventar- und Simulationsergebnisse bleiben lokal.
- Keine Telemetrie, keine Analytics und kein Upload zu Raidbots oder Wago.
- Beim normalen Start werden keine Analyse, Installation oder Netzwerkanfrage ausgeführt.
- Analysen und Staging-Daten liegen unter %LOCALAPPDATA%\LocalGearAdvisor.
- Die Live-Installation ist optional und standardmäßig deaktiviert.
- Während Wow.exe läuft oder sein Zustand nicht sicher feststellbar ist, verändert der
  Helper keine Addon-Dateien. WoW vor einer ausdrücklich gewählten Installation beenden.
- SavedVariables werden vom Helper nicht extern verändert.

SimulationCraft-Hinweise
SimulationCraft kann für neue Spielmechaniken einen Hinweis wie
„implementation_not_yet_verified“ ausgeben. Ein erfolgreich berechnetes Ergebnis ist
kein Helper-Absturz; neue oder unbekannte Fehler bleiben fail-closed.

Prüfsumme und SmartScreen
Die EXE ist derzeit nicht kommerziell codesigniert. Windows SmartScreen kann deshalb eine
Warnung anzeigen. Nicht blind umgehen: zuerst die SHA-256-Prüfsumme mit SHA256SUMS.txt
vergleichen, z. B. in PowerShell:

  Get-FileHash .\LocalGearAdvisor.exe -Algorithm SHA256

Deinstallation
- EXE und entpackten Ordner löschen.
- Optional lokale Helper-Daten löschen:
  %LOCALAPPDATA%\LocalGearAdvisor
- Das WoW-Addon wird dadurch nicht automatisch entfernt.

Projekt und Quellcode
https://github.com/Madchristian/local-gear-advisor

Lizenz: All Rights Reserved. Siehe Projekt-Repository.
