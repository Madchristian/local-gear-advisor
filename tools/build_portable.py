from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

_APPLICATION = "LocalGearAdvisor"
_RELEASE_FILES = (
    "LocalGearAdvisor.exe",
    "README-DE.txt",
    "README-EN.txt",
    "SHA256SUMS.txt",
)
_HASHED_FILES = _RELEASE_FILES[:-1]
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pyinstaller_command(*, root: Path, python: Path) -> list[str]:
    root = root.resolve()
    return [
        str(python),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--noupx",
        "--console",
        "--hide-console",
        "hide-early",
        "--name",
        _APPLICATION,
        "--distpath",
        str(root / "build" / "portable" / "dist"),
        "--workpath",
        str(root / "build" / "portable" / "work"),
        "--specpath",
        str(root / "build" / "portable" / "spec"),
        "--paths",
        str(root / "src"),
        "--add-data",
        f"{root / 'addon' / 'LocalGearAdvisor'};local_gear_advisor/addon_template",
        "--add-data",
        str(root / "src" / "local_gear_advisor" / "data" / "spec_registry.json")
        + ";local_gear_advisor/data",
        "--add-data",
        f"{root / 'portable' / 'LocalGearAdvisor.ico'};local_gear_advisor/portable_assets",
        "--icon",
        str(root / "portable" / "LocalGearAdvisor.ico"),
        "--version-file",
        str(root / "portable" / "version_info.txt"),
        str(root / "portable_entry.py"),
    ]


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (0o100644 & 0xFFFF) << 16
    return info


def create_release_bundle(
    *,
    executable: Path,
    readme_de: Path,
    readme_en: Path,
    output_dir: Path,
    version: str,
) -> Path:
    if executable.name != "LocalGearAdvisor.exe":
        raise ValueError("portable executable must be named LocalGearAdvisor.exe")
    if not _VERSION_RE.fullmatch(version):
        raise ValueError("portable version must be semantic X.Y.Z")
    sources = {
        "LocalGearAdvisor.exe": executable,
        "README-DE.txt": readme_de,
        "README-EN.txt": readme_en,
    }
    payloads: dict[str, bytes] = {}
    for name, source in sources.items():
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"release input is not a regular file: {source}")
        payloads[name] = source.read_bytes()
    if not payloads["LocalGearAdvisor.exe"].startswith(b"MZ"):
        raise ValueError("portable executable has no Windows PE header")
    for name in ("README-DE.txt", "README-EN.txt"):
        payloads[name].decode("utf-8")

    manifest = "\n".join(f"{_sha256(payloads[name])}  {name}" for name in _HASHED_FILES)
    payloads["SHA256SUMS.txt"] = (manifest + "\n").encode("ascii")

    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"LocalGearAdvisor-Helper-{version}.zip"
    temporary = output_dir / f".{archive.name}.tmp"
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary, "w", strict_timestamps=True) as zf:
        for name in _RELEASE_FILES:
            zf.writestr(_zip_info(name), payloads[name])
    temporary.replace(archive)
    verify_release_bundle(archive)
    return archive


def verify_release_bundle(archive: Path) -> dict[str, str]:
    if not archive.is_file() or archive.is_symlink():
        raise ValueError("release ZIP is not a regular file")
    with zipfile.ZipFile(archive) as zf:
        if zf.testzip() is not None:
            raise ValueError("release ZIP failed CRC validation")
        if zf.namelist() != list(_RELEASE_FILES):
            raise ValueError("release ZIP inventory is not canonical")
        if len(set(zf.namelist())) != len(_RELEASE_FILES):
            raise ValueError("release ZIP contains duplicate names")
        payloads = {name: zf.read(name) for name in _RELEASE_FILES}
    expected_manifest = "\n".join(
        f"{_sha256(payloads[name])}  {name}" for name in _HASHED_FILES
    ) + "\n"
    if payloads["SHA256SUMS.txt"] != expected_manifest.encode("ascii"):
        raise ValueError("release checksum manifest does not match ZIP bytes")
    return {name: _sha256(payloads[name]) for name in _RELEASE_FILES}


def build(root: Path, *, python: Path, version: str) -> Path:
    root = root.resolve()
    build_root = root / "build" / "portable"
    if build_root.exists():
        shutil.rmtree(build_root)
    subprocess.run(  # noqa: S603 - argv is fully constructed from trusted repository paths
        pyinstaller_command(root=root, python=python),
        cwd=root,
        check=True,
        shell=False,
        timeout=600,
    )
    executable = build_root / "dist" / "LocalGearAdvisor.exe"
    return create_release_bundle(
        executable=executable,
        readme_de=root / "portable" / "README-DE.txt",
        readme_en=root / "portable" / "README-EN.txt",
        output_dir=root / "dist",
        version=version,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="0.2.1")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    archive = build(root, python=Path(sys.executable), version=args.version)
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
