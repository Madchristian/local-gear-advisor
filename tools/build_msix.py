"""Build a Store-ready MSIX package from the reviewed portable executable."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

_ASSET_NAMES = (
    "Square150x150Logo.png",
    "Square44x44Logo.png",
    "StoreLogo.png",
    "Wide310x150Logo.png",
)

_IDENTITY_RE = re.compile(r"^[A-Za-z0-9.-]{3,50}$")


def _validate_identity(identity_name: str, publisher: str, version: str) -> None:
    if not _IDENTITY_RE.fullmatch(identity_name):
        raise ValueError("MSIX identity name is invalid")
    if not publisher.startswith("CN=") or any(ord(char) < 32 for char in publisher):
        raise ValueError("MSIX publisher must be a certificate subject beginning with CN=")
    parts = version.split(".")
    if len(parts) != 4 or any(not part.isdigit() for part in parts):
        raise ValueError("MSIX version must contain four numeric components")
    if any(int(part) > 65535 for part in parts):
        raise ValueError("MSIX version components must be at most 65535")


def render_manifest(
    *,
    identity_name: str,
    publisher: str,
    publisher_display_name: str = "Madchristian",
    version: str = "0.2.1.0",
) -> str:
    _validate_identity(identity_name, publisher, version)
    if not publisher_display_name.strip() or any(ord(char) < 32 for char in publisher_display_name):
        raise ValueError("MSIX publisher display name is invalid")
    identity_name = escape(identity_name, {'"': "&quot;"})
    publisher = escape(publisher, {'"': "&quot;"})
    publisher_display_name = escape(publisher_display_name, {'"': "&quot;"})
    version = escape(version, {'"': "&quot;"})
    return f'''<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:uap10="http://schemas.microsoft.com/appx/manifest/uap/windows10/10"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap uap10 rescap">
  <Identity
    Name="{identity_name}"
    Publisher="{publisher}"
    Version="{version}"
    ProcessorArchitecture="x64" />
  <Properties>
    <DisplayName>Local Gear Advisor</DisplayName>
    <PublisherDisplayName>{publisher_display_name}</PublisherDisplayName>
    <Description>Local-only gear analysis companion for World of Warcraft</Description>
    <Logo>Assets\\StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily
      Name="Windows.Desktop"
      MinVersion="10.0.19041.0"
      MaxVersionTested="10.0.26200.0" />
  </Dependencies>
  <Resources>
    <Resource Language="de-de" />
    <Resource Language="en-us" />
  </Resources>
  <Applications>
    <Application
      Id="LocalGearAdvisor"
      Executable="LocalGearAdvisor.exe"
      uap10:RuntimeBehavior="packagedClassicApp"
      uap10:TrustLevel="mediumIL">
      <uap:VisualElements
        AppListEntry="default"
        DisplayName="Local Gear Advisor"
        Description="Local-only gear analysis companion"
        BackgroundColor="#101820"
        Square150x150Logo="Assets\\Square150x150Logo.png"
        Square44x44Logo="Assets\\Square44x44Logo.png">
        <uap:DefaultTile Wide310x150Logo="Assets\\Wide310x150Logo.png" />
      </uap:VisualElements>
    </Application>
  </Applications>
  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
'''


def stage_package(
    *,
    root: Path,
    executable: Path,
    output_dir: Path,
    identity_name: str,
    publisher: str,
    version: str,
    publisher_display_name: str = "Madchristian",
) -> Path:
    executable_bytes = executable.read_bytes()
    if not executable_bytes.startswith(b"MZ"):
        raise ValueError("portable executable is not a Windows PE file")
    manifest = render_manifest(
        identity_name=identity_name,
        publisher=publisher,
        publisher_display_name=publisher_display_name,
        version=version,
    )
    asset_root = root / "portable" / "msix" / "Assets"
    missing = [name for name in _ASSET_NAMES if not (asset_root / name).is_file()]
    if missing:
        raise FileNotFoundError(f"missing MSIX assets: {', '.join(missing)}")
    if output_dir.is_symlink():
        raise ValueError("MSIX staging directory must not be a symlink")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    (output_dir / "Assets").mkdir(parents=True)
    (output_dir / "AppxManifest.xml").write_text(manifest, encoding="utf-8", newline="\n")
    (output_dir / "LocalGearAdvisor.exe").write_bytes(executable_bytes)
    for name in _ASSET_NAMES:
        shutil.copyfile(asset_root / name, output_dir / "Assets" / name)
    return output_dir


def makeappx_command(*, tool: Path, stage: Path, output: Path) -> list[str]:
    return [str(tool), "pack", "/o", "/d", str(stage), "/p", str(output)]


def find_makeappx(
    sdk_bin: Path = Path(r"C:\Program Files (x86)\Windows Kits\10\bin"),
) -> Path:
    candidates = list(sdk_bin.glob("*/x64/makeappx.exe"))
    if not candidates:
        raise FileNotFoundError(f"x64 makeappx.exe not found under {sdk_bin}")

    def version_key(path: Path) -> tuple[int, ...]:
        try:
            return tuple(int(part) for part in path.parents[1].name.split("."))
        except ValueError:
            return ()

    return max(candidates, key=version_key)


def is_store_identity(identity_name: str, publisher: str) -> bool:
    lowered_publisher = publisher.lower()
    return not (
        identity_name.endswith((".Test", ".UnsignedTest"))
        or publisher in {"CN=LocalGearAdvisor-Test", "CN=Unsigned"}
        or "oid.2.25.311729368913984317654407730594956997722=1" in lowered_publisher
    )


def store_submission_ready(
    identity_name: str,
    publisher: str,
    *,
    partner_center_confirmed: bool,
) -> bool:
    return partner_center_confirmed and is_store_identity(identity_name, publisher)


def verify_msix(package: Path, *, expected_executable: bytes) -> dict[str, object]:
    expected = {
        "AppxManifest.xml",
        "AppxBlockMap.xml",
        "[Content_Types].xml",
        "LocalGearAdvisor.exe",
        *(f"Assets/{name}" for name in _ASSET_NAMES),
    }
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("MSIX contains duplicate members")
        if any(
            name.startswith(("/", "\\")) or "\\" in name or ".." in Path(name).parts
            for name in names
        ):
            raise ValueError("MSIX contains an unsafe member path")
        signed = "AppxSignature.p7x" in names
        allowed = expected | ({"AppxSignature.p7x"} if signed else set())
        if set(names) != allowed:
            raise ValueError("MSIX inventory differs from the allowlist")
        bad_member = archive.testzip()
        if bad_member is not None:
            raise ValueError(f"MSIX CRC failure: {bad_member}")
        if archive.read("LocalGearAdvisor.exe") != expected_executable:
            raise ValueError("MSIX executable differs from the reviewed executable")
    return {"members": sorted(names), "signed": signed}


def build_package(
    *,
    root: Path,
    executable: Path,
    output: Path,
    identity_name: str,
    publisher: str,
    version: str,
    makeappx: Path,
    publisher_display_name: str = "Madchristian",
) -> dict[str, object]:
    executable_bytes = executable.read_bytes()
    stage = stage_package(
        root=root,
        executable=executable,
        output_dir=root / "build" / "msix" / "stage",
        identity_name=identity_name,
        publisher=publisher,
        version=version,
        publisher_display_name=publisher_display_name,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    command = makeappx_command(tool=makeappx, stage=stage, output=output)
    result = subprocess.run(  # noqa: S603 - executable is an explicit Windows SDK path
        command,
        capture_output=True,
        check=False,
        shell=False,
        timeout=300,
    )
    if result.returncode != 0:
        detail = (result.stdout + result.stderr).decode("mbcs", errors="replace").strip()
        raise RuntimeError(f"MakeAppx failed with exit code {result.returncode}: {detail}")
    report = verify_msix(output, expected_executable=executable_bytes)
    report.update(
        {
            "path": str(output.resolve()),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "size": output.stat().st_size,
        }
    )
    return report


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity-name", default="Madchristian.LocalGearAdvisor.Test")
    parser.add_argument("--publisher", default="CN=LocalGearAdvisor-Test")
    parser.add_argument("--publisher-display-name", default="Madchristian")
    parser.add_argument("--version", default="0.2.1.0")
    parser.add_argument(
        "--executable",
        type=Path,
        default=root / "build" / "portable" / "dist" / "LocalGearAdvisor.exe",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "dist" / "LocalGearAdvisor-MSIX-Test-0.2.1.msix",
    )
    parser.add_argument("--makeappx", type=Path, default=None)
    parser.add_argument(
        "--partner-center-identity",
        action="store_true",
        help="confirm that identity name and publisher were copied from Partner Center",
    )
    args = parser.parse_args(argv)
    if args.partner_center_identity and not is_store_identity(args.identity_name, args.publisher):
        parser.error("test or unsigned identities cannot be submitted to the Store")
    report = build_package(
        root=root,
        executable=args.executable,
        output=args.output,
        identity_name=args.identity_name,
        publisher=args.publisher,
        publisher_display_name=args.publisher_display_name,
        version=args.version,
        makeappx=args.makeappx or find_makeappx(),
    )
    report["store_submittable"] = store_submission_ready(
        args.identity_name,
        args.publisher,
        partner_center_confirmed=args.partner_center_identity,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
