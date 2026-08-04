from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from tools import build_msix

ROOT = Path(__file__).parents[1]


def test_render_manifest_declares_x64_packaged_classic_full_trust_app() -> None:
    manifest = build_msix.render_manifest(
        identity_name="Madchristian.LocalGearAdvisor.Test",
        publisher="CN=LocalGearAdvisor-Test",
        publisher_display_name="madchristian",
        version="0.2.1.0",
    )
    root = ET.fromstring(manifest)  # noqa: S314 - parses our generated static manifest
    ns = {
        "f": "http://schemas.microsoft.com/appx/manifest/foundation/windows10",
        "uap": "http://schemas.microsoft.com/appx/manifest/uap/windows10",
        "uap10": "http://schemas.microsoft.com/appx/manifest/uap/windows10/10",
        "rescap": "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities",
    }

    identity = root.find("f:Identity", ns)
    assert identity is not None
    assert identity.attrib == {
        "Name": "Madchristian.LocalGearAdvisor.Test",
        "Publisher": "CN=LocalGearAdvisor-Test",
        "Version": "0.2.1.0",
        "ProcessorArchitecture": "x64",
    }
    application = root.find("f:Applications/f:Application", ns)
    assert application is not None
    assert application.attrib["Executable"] == "LocalGearAdvisor.exe"
    assert application.attrib[f"{{{ns['uap10']}}}RuntimeBehavior"] == "packagedClassicApp"
    assert application.attrib[f"{{{ns['uap10']}}}TrustLevel"] == "mediumIL"
    capability = root.find("f:Capabilities/rescap:Capability", ns)
    assert capability is not None
    assert capability.attrib["Name"] == "runFullTrust"
    publisher_display_name = root.find("f:Properties/f:PublisherDisplayName", ns)
    assert publisher_display_name is not None
    assert publisher_display_name.text == "madchristian"
    visual = application.find("uap:VisualElements", ns)
    assert visual is not None
    assert visual.attrib["AppListEntry"] == "default"


def test_render_manifest_rejects_unusable_identity_values() -> None:
    with pytest.raises(ValueError, match="identity name"):
        build_msix.render_manifest(identity_name="bad name", publisher="CN=Test")
    with pytest.raises(ValueError, match="publisher"):
        build_msix.render_manifest(identity_name="Good.Name", publisher="Test")
    with pytest.raises(ValueError, match="four numeric"):
        build_msix.render_manifest(
            identity_name="Good.Name", publisher="CN=Test", version="0.2.1"
        )


def test_stage_package_has_exact_allowlisted_payload(tmp_path: Path) -> None:
    executable = tmp_path / "LocalGearAdvisor.exe"
    executable.write_bytes(b"MZ\x00store-test")

    stage = build_msix.stage_package(
        root=ROOT,
        executable=executable,
        output_dir=tmp_path / "stage",
        identity_name="Madchristian.LocalGearAdvisor.Test",
        publisher="CN=LocalGearAdvisor-Test",
        publisher_display_name="madchristian",
        version="0.2.1.0",
    )

    files = sorted(
        str(path.relative_to(stage)).replace("\\", "/")
        for path in stage.rglob("*")
        if path.is_file()
    )
    assert files == [
        "AppxManifest.xml",
        "Assets/Square150x150Logo.png",
        "Assets/Square44x44Logo.png",
        "Assets/StoreLogo.png",
        "Assets/Wide310x150Logo.png",
        "LocalGearAdvisor.exe",
    ]
    assert (stage / "LocalGearAdvisor.exe").read_bytes() == executable.read_bytes()
    assert b"LocalGearAdvisor-Test" in (stage / "AppxManifest.xml").read_bytes()
    assert b"<PublisherDisplayName>madchristian</PublisherDisplayName>" in (
        stage / "AppxManifest.xml"
    ).read_bytes()


def test_checked_in_msix_assets_have_expected_png_dimensions() -> None:
    expected = {
        "Square150x150Logo.png": (150, 150),
        "Square44x44Logo.png": (44, 44),
        "StoreLogo.png": (50, 50),
        "Wide310x150Logo.png": (310, 150),
    }
    for name, dimensions in expected.items():
        data = (ROOT / "portable" / "msix" / "Assets" / name).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        assert struct.unpack(">II", data[16:24]) == dimensions


def test_makeappx_command_uses_pack_overwrite_and_exact_paths(tmp_path: Path) -> None:
    tool = Path(r"C:\WindowsSDK\makeappx.exe")
    stage = tmp_path / "stage"
    output = tmp_path / "LocalGearAdvisor-Store-0.2.1.msix"

    assert build_msix.makeappx_command(tool=tool, stage=stage, output=output) == [
        str(tool),
        "pack",
        "/o",
        "/d",
        str(stage),
        "/p",
        str(output),
    ]


def test_find_makeappx_chooses_newest_x64_windows_sdk(tmp_path: Path) -> None:
    older = tmp_path / "10.0.19041.0" / "x64" / "makeappx.exe"
    newer = tmp_path / "10.0.22621.0" / "x64" / "makeappx.exe"
    older.parent.mkdir(parents=True)
    newer.parent.mkdir(parents=True)
    older.write_bytes(b"")
    newer.write_bytes(b"")

    assert build_msix.find_makeappx(tmp_path) == newer
    with pytest.raises(FileNotFoundError, match="makeappx"):
        build_msix.find_makeappx(tmp_path / "missing")


def test_only_partner_center_identity_is_reported_as_store_submittable() -> None:
    assert not build_msix.is_store_identity(
        "Madchristian.LocalGearAdvisor.Test", "CN=LocalGearAdvisor-Test"
    )
    assert not build_msix.is_store_identity(
        "Madchristian.LocalGearAdvisor.UnsignedTest", "CN=Unsigned"
    )
    assert not build_msix.is_store_identity(
        "Madchristian.LocalGearAdvisor.UnsignedTest",
        "CN=Test, OID.2.25.311729368913984317654407730594956997722=1",
    )
    assert build_msix.is_store_identity(
        "12345Madchristian.LocalGearAdvisor",
        "CN=01234567-89ab-cdef-0123-456789abcdef",
    )
    assert not build_msix.store_submission_ready(
        "12345Madchristian.LocalGearAdvisor",
        "CN=01234567-89ab-cdef-0123-456789abcdef",
        partner_center_confirmed=False,
    )
    assert build_msix.store_submission_ready(
        "12345Madchristian.LocalGearAdvisor",
        "CN=01234567-89ab-cdef-0123-456789abcdef",
        partner_center_confirmed=True,
    )


def test_main_passes_partner_center_publisher_display_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_build_package(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(build_msix, "build_package", fake_build_package)
    assert (
        build_msix.main(
            [
                "--identity-name",
                "madchristian.LocalGearAdvisor",
                "--publisher",
                "CN=9492778C-162D-411C-BED3-095491D59DB3",
                "--publisher-display-name",
                "madchristian",
                "--partner-center-identity",
                "--makeappx",
                r"C:\WindowsSDK\makeappx.exe",
            ]
        )
        == 0
    )
    assert captured["publisher_display_name"] == "madchristian"


def test_verify_msix_requires_exact_unsigned_inventory_and_exe_bytes(
    tmp_path: Path,
) -> None:
    package = tmp_path / "test.msix"
    executable = b"MZ\x00verified"
    members = {
        "AppxManifest.xml": b"<Package />",
        "AppxBlockMap.xml": b"<BlockMap />",
        "[Content_Types].xml": b"<Types />",
        "LocalGearAdvisor.exe": executable,
        **{
            f"Assets/{name}": b"\x89PNG\r\n\x1a\n"
            for name in (
                "Square150x150Logo.png",
                "Square44x44Logo.png",
                "StoreLogo.png",
                "Wide310x150Logo.png",
            )
        },
    }
    with zipfile.ZipFile(package, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)

    report = build_msix.verify_msix(package, expected_executable=executable)

    assert report["signed"] is False
    assert report["members"] == sorted(members)
    with zipfile.ZipFile(package, "a") as archive:
        archive.writestr("simc.exe", b"forbidden")
    with pytest.raises(ValueError, match="inventory"):
        build_msix.verify_msix(package, expected_executable=executable)
