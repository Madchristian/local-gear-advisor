from __future__ import annotations

import hashlib
import tomllib
import zipfile
from pathlib import Path

from tools import build_portable


def test_portable_build_dependencies_and_version_are_pinned() -> None:
    root = Path(__file__).parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    assert config["project"]["version"] == "0.2.1"
    assert "pyinstaller==6.21.0" in config["dependency-groups"]["dev"]
    assert "pyinstaller-hooks-contrib==2026.6" in config["dependency-groups"]["dev"]


def test_pyinstaller_command_is_single_file_console_capable_and_console_hidden(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    command = build_portable.pyinstaller_command(root=root, python=Path("python.exe"))

    assert command[:3] == ["python.exe", "-m", "PyInstaller"]
    assert "--onefile" in command
    assert "--console" in command
    assert "--noupx" in command
    assert command[command.index("--hide-console") + 1] == "hide-early"
    assert command[command.index("--name") + 1] == "LocalGearAdvisor"
    assert command[command.index("--paths") + 1] == str(root / "src")
    assert command[command.index("--add-data") + 1] == (
        f"{root / 'addon' / 'LocalGearAdvisor'};local_gear_advisor/addon_template"
    )
    assert (
        f"{root / 'src' / 'local_gear_advisor' / 'data' / 'spec_registry.json'};"
        "local_gear_advisor/data" in command
    )
    assert (
        f"{root / 'portable' / 'LocalGearAdvisor.ico'};local_gear_advisor/portable_assets"
        in command
    )
    assert command[command.index("--version-file") + 1] == str(
        root / "portable" / "version_info.txt"
    )
    assert command[-1] == str(root / "portable_entry.py")


def test_release_bundle_has_exact_inventory_crc_and_inner_hashes(tmp_path: Path) -> None:
    exe = tmp_path / "LocalGearAdvisor.exe"
    exe.write_bytes(b"MZ\x00portable-test")
    readme_de = tmp_path / "README-DE.txt"
    readme_en = tmp_path / "README-EN.txt"
    readme_de.write_text("Deutsch\n", encoding="utf-8")
    readme_en.write_text("English\n", encoding="utf-8")
    output = tmp_path / "release"

    archive = build_portable.create_release_bundle(
        executable=exe,
        readme_de=readme_de,
        readme_en=readme_en,
        output_dir=output,
        version="0.2.1",
    )

    assert archive.name == "LocalGearAdvisor-Helper-0.2.1.zip"
    with zipfile.ZipFile(archive) as zf:
        assert zf.testzip() is None
        assert zf.namelist() == [
            "LocalGearAdvisor.exe",
            "README-DE.txt",
            "README-EN.txt",
            "SHA256SUMS.txt",
        ]
        payloads = {name: zf.read(name) for name in zf.namelist()}
    manifest = payloads["SHA256SUMS.txt"].decode("ascii").splitlines()
    assert manifest == [
        f"{hashlib.sha256(payloads[name]).hexdigest()}  {name}"
        for name in ("LocalGearAdvisor.exe", "README-DE.txt", "README-EN.txt")
    ]
    assert build_portable.verify_release_bundle(archive) == {
        name: hashlib.sha256(content).hexdigest() for name, content in payloads.items()
    }


def test_release_bundle_refuses_wrong_executable_basename(tmp_path: Path) -> None:
    exe = tmp_path / "other.exe"
    exe.write_bytes(b"MZ")
    de = tmp_path / "README-DE.txt"
    en = tmp_path / "README-EN.txt"
    de.write_text("de", encoding="utf-8")
    en.write_text("en", encoding="utf-8")

    try:
        build_portable.create_release_bundle(
            executable=exe,
            readme_de=de,
            readme_en=en,
            output_dir=tmp_path / "out",
            version="0.2.1",
        )
    except ValueError as exc:
        assert "LocalGearAdvisor.exe" in str(exc)
    else:
        raise AssertionError("wrong executable basename was accepted")
