LOCAL GEAR ADVISOR – PORTABLE WINDOWS HELPER 0.2.1
=================================================

Compatibility
- Windows 10/11, 64-bit
- Local Gear Advisor WoW addon 0.2.0 (LGA2 transport format)
- World of Warcraft Retail

Getting started
1. Extract the complete ZIP into a normal folder.
2. Start LocalGearAdvisor.exe. Python and administrator rights are not required.
3. Select an official local simc.exe. SimulationCraft is not bundled for licensing,
   provenance, and update-safety reasons.
4. In WoW, use the SimulationCraft addon to create a complete /simc export.
5. Paste the export into the helper and run the local analysis.
6. Click “Copy import text” and paste it into the WoW addon's Import tab.

Security and privacy
- Character, inventory, and simulation results remain local.
- No telemetry, analytics, or uploads to Raidbots or Wago.
- Normal startup performs no analysis, installation, or network request.
- Analysis and staging data are stored under %LOCALAPPDATA%\LocalGearAdvisor.
- Live installation is optional and disabled by default.
- While Wow.exe is running, or its state cannot be established safely, the helper does
  not modify addon files. Close WoW before explicitly requesting an installation.
- The helper never edits WoW SavedVariables externally.

SimulationCraft notices
SimulationCraft may emit notices such as “implementation_not_yet_verified” for new game
mechanics. A successfully calculated result is not a helper crash; new or unknown errors
continue to fail closed.

Checksum and SmartScreen
The EXE is not currently commercially code-signed, so Windows SmartScreen may display a
warning. Do not bypass it blindly. First compare the SHA-256 checksum with
SHA256SUMS.txt, for example in PowerShell:

  Get-FileHash .\LocalGearAdvisor.exe -Algorithm SHA256

Uninstall
- Delete the EXE and extracted folder.
- Optionally delete local helper data:
  %LOCALAPPDATA%\LocalGearAdvisor
- This does not automatically remove the WoW addon.

Project and source code
https://github.com/Madchristian/local-gear-advisor

License: All Rights Reserved. See the project repository.
