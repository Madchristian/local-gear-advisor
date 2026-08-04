# Microsoft Store submission: Local Gear Advisor 0.2.1

This directory contains the reviewed MSIX build contract and Store assets. The checked-in build defaults deliberately create a non-submittable test identity. Never upload a package carrying `.Test`, `.UnsignedTest`, `CN=LocalGearAdvisor-Test`, `CN=Unsigned`, or Microsoft's unsigned-test OID.

## Completed local evidence

- Windows SDK 10.0.22621 `MakeAppx.exe` successfully built the package.
- The package contains only the reviewed `LocalGearAdvisor.exe`, manifest, four logo assets, and generated MSIX metadata.
- A temporary self-signed package was installed on Windows, launched through its registered AppsFolder identity, and removed again.
- The installed executable passed `--portable-smoke-test`: helper 0.2.1, addon 0.2.0, schema 2, transport LGA2, 40 specs, and eight addon files.
- The installed GUI opened from `C:\Program Files\WindowsApps`, showed the app icon and complete controls, and closed normally.
- Package and temporary test certificate were removed and their absence verified.
- The test certificate is not a distribution certificate and must never be published.

## Partner Center identity

The owner completed registration, created the product, and supplied these public package values exactly as shown by Partner Center:

```text
Package/Identity/Name: madchristian.LocalGearAdvisor
Package/Identity/Publisher: CN=9492778C-162D-411C-BED3-095491D59DB3
Package/Properties/PublisherDisplayName: madchristian
Package Family Name: madchristian.LocalGearAdvisor_n4e29js5tmcqc
Store ID: 9N589X7GNBBX
Reserved product display name: Local Gear Advisor
```

The PFN and Store ID are verification metadata; they are not substituted for the manifest identity values. Do not place account credentials, verification documents, tokens, or recovery codes in this repository or chat.

## Final package command

Build the unsigned Store upload package from the reviewed portable EXE:

```text
.venv\Scripts\python.exe tools\build_msix.py ^
  --identity-name "madchristian.LocalGearAdvisor" ^
  --publisher "CN=9492778C-162D-411C-BED3-095491D59DB3" ^
  --publisher-display-name "madchristian" ^
  --partner-center-identity ^
  --output dist\LocalGearAdvisor-Store-0.2.1.msix
```

The final package must report `store_submittable: true`, but that flag is only an operator declaration. Before upload, compare Name, Publisher, PublisherDisplayName, product DisplayName, PFN, and Store ID manually against Partner Center and repeat every package/privacy/Defender gate. The Microsoft Store re-signs an accepted MSIX; do not self-sign the upload package.

## Store listing — German

Short description:

```text
Lokale SimulationCraft-Ausrüstungsvergleiche für WoW Retail – ohne Cloud, Telemetrie oder Raidbots-Upload.
```

Description:

```text
Local Gear Advisor vergleicht Ausrüstung für World of Warcraft Retail vollständig lokal mit einer vom Nutzer ausgewählten SimulationCraft-Installation.

Ein vollständiger /simc-Export einschließlich Taschen und geladener Bankbereiche wird lokal verarbeitet. Charakter-, Inventar-, Simulations- und Ergebnisdaten verlassen den PC nicht. Die Anwendung enthält keine Telemetrie, Werbung, Cloud-Anbindung oder Raidbots-Integration.

Ergebnisse werden über einen versionierten, integritätsgeprüften Copy/Paste-Transport in das separat installierte WoW-Addon Local Gear Advisor übernommen. Helper 0.2.1 ist für Addon 0.2.0, Schema 2 und Transport LGA2 bestimmt.

Die geprüfte Addon-Vorlage ist in der Anwendung enthalten. Ihre Installation ist optional, standardmäßig deaktiviert und erfolgt nur nach einer ausdrücklichen Nutzeraktion. `simc.exe` wird weder mitgeliefert noch heruntergeladen. Die Anwendung öffnet die offizielle SimulationCraft-Downloadseite nur nach einem ausdrücklichen Klick.
```

Screenshot caption:

```text
Lokale Analyseoberfläche mit bewusst deaktivierter automatischer Addon-Installation.
```

## Store listing — English

Short description:

```text
Local SimulationCraft gear comparisons for WoW Retail—without cloud, telemetry, or Raidbots uploads.
```

Description:

```text
Local Gear Advisor compares equipment for World of Warcraft Retail entirely on the user's PC using a user-selected SimulationCraft installation.

A complete /simc export, including bags and loaded bank areas, is processed locally. Character, inventory, simulation, and result data never leaves the PC. The app has no telemetry, advertising, cloud backend, or Raidbots integration.

Results are transferred to the separately installed Local Gear Advisor WoW addon through a versioned, integrity-checked copy/paste format. Helper 0.2.1 is intended for addon 0.2.0, schema 2, and LGA2 transport.

A reviewed addon template is included in the app. Installation is optional, disabled by default, and occurs only after an explicit user action. `simc.exe` is neither bundled nor downloaded. The app opens the official SimulationCraft download page only after an explicit click.
```

Screenshot caption:

```text
Local analysis interface with automatic addon installation disabled by default.
```

## Submission fields

- Category: Utilities & tools
- Pricing: Free
- Markets: start with supported Windows 10/11 desktop markets
- Architecture: x64
- Minimum OS: Windows 10 version 2004 (`10.0.19041.0`)
- Accounts/login: none
- In-app purchases: none
- Ads: none
- Privacy policy URL after tag publication: `https://github.com/Madchristian/local-gear-advisor/blob/v0.2.1/PRIVACY.md`
- Support URL: `https://github.com/Madchristian/local-gear-advisor/issues`
- Website: `https://github.com/Madchristian/local-gear-advisor`

Restricted capability explanation for `runFullTrust`:

```text
Local Gear Advisor is a packaged classic Windows desktop application. Full-trust/medium-IL execution is required to let the user select and run their existing local simc.exe process, read explicitly selected /simc exports and SimulationCraft JSON reports, access a user-selected World of Warcraft addon directory, and write local results under the user's LocalAppData. It does not request elevation, install services or drivers, modify system configuration, collect telemetry, or transmit character/simulation data.
```

Certification notes:

```text
The app is local-only. On first start, select an independently installed supported simc.exe and the LocalGearAdvisor WoW addon directory. Automatic installation is off by default. The read-only startup and the package contract can be verified without personal data. The app opens https://www.simulationcraft.org/download.html only after the user clicks the download button.
```

## Final gates after Partner Center identity is supplied

1. Rebuild the MSIX from the exact final commit and reviewed EXE.
2. Verify exact package inventory, CRC, block map, manifest identity, executable byte equality, and SHA-256.
3. Run privacy/secret scans over manifest, assets, embedded executable, and screenshot.
4. Run Microsoft Defender against the exact final MSIX.
5. Obtain an independent review tied to the final source tree and package hash.
6. Upload only the reviewed unsigned Store MSIX.
7. Resolve certification feedback fail-closed; never weaken process, privacy, or LGA2 checks merely to pass certification.
8. After publication, install from the public Store listing and repeat smoke, GUI, external SimulationCraft selection, and copy/paste import tests.
