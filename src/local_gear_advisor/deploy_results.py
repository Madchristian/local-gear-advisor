from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import uuid
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from .safety import WowState, query_wow_state
from .state import load_state, render_aggregate_lua

CODE_FILE_NAMES = (
    "LocalGearAdvisor.toc",
    "Localization.lua",
    "Sha256.lua",
    "Core.lua",
    "Import.lua",
    "Minimap.lua",
    "UI.lua",
)
_EXPECTED_FILES = frozenset(CODE_FILE_NAMES) | {"Results.lua"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TIMESTAMP_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")


class DeployError(RuntimeError):
    """A result-only live deployment was blocked or could not be verified."""


@dataclass(frozen=True)
class DeployReceipt:
    results_sha256: str
    backup: Path
    receipt: Path
    addon_dir: Path


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _packaged_addon_asset(name: str) -> bytes:
    package = resources.files("local_gear_advisor").joinpath("addon_template")
    try:
        return package.joinpath(name).read_bytes()
    except FileNotFoundError as exc:
        source = Path(__file__).resolve().parents[2] / "addon" / "LocalGearAdvisor" / name
        if not source.is_file():
            raise DeployError("packaged addon assets are unavailable") from exc
        return source.read_bytes()


def expected_addon_assets() -> dict[str, bytes]:
    """Every non-Results.lua addon file, keyed by filename, exactly as packaged.

    Used both to seed a fresh staging/install copy of the addon code and to
    verify (byte-for-byte) that an already-installed addon's code is exactly
    this release before a Results.lua-only live publish is allowed to touch
    it -- so the live path never has to guess whether it's safe to run
    against a hand-modified or out-of-date install.
    """
    return {name: _packaged_addon_asset(name) for name in CODE_FILE_NAMES}


def extract_addon_template(destination: Path) -> Path:
    """Create a fresh byte-verified manual-install source; never writes to WoW."""
    destination = destination.resolve()
    if destination.exists():
        raise DeployError(f"staging destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    assets = expected_addon_assets()
    assets["Results.lua"] = _packaged_addon_asset("Results.lua")

    def readback(directory: Path) -> dict[str, bytes]:
        entries = list(directory.iterdir())
        if {entry.name for entry in entries} != set(assets):
            return {}
        observed: dict[str, bytes] = {}
        for entry in entries:
            _assert_plain(entry, directory=False)
            observed[entry.name] = entry.read_bytes()
        return observed

    private = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.staging-",
            dir=destination.parent,
        )
    )
    try:
        for name, content in assets.items():
            target = private / name
            with target.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        if readback(private) != assets:
            raise DeployError("staged addon failed byte-for-byte readback")
        if destination.exists():
            raise DeployError(f"staging destination already exists: {destination}")
        # On the supported Windows platform os.rename is create-only for a
        # directory target: a racing destination makes this fail without
        # replacing or deleting that foreign generation.
        os.rename(private, destination)
        if readback(destination) != assets:
            raise DeployError("published addon failed byte-for-byte readback")
    except Exception as exc:
        # Never delete by pathname here: another process could replace even a
        # previously identity-checked directory between stat() and rmtree().
        # Retaining staging paths is the only fully generation-safe failure
        # behavior available via the stdlib.
        if hasattr(exc, "add_note"):
            exc.add_note(
                "staging paths retained for inspection: "
                f"private={private}; destination={destination}"
            )
        raise
    return destination


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_plain(path: Path, *, directory: bool) -> None:
    if directory and not path.is_dir():
        raise DeployError(f"required directory is missing: {path}")
    if not directory and not path.is_file():
        raise DeployError(f"required file is missing: {path}")
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise DeployError(f"cannot inspect deployment path: {path}: {exc}") from exc
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    attributes = getattr(metadata, "st_file_attributes", 0)
    if path.is_symlink() or attributes & reparse:
        raise DeployError(f"reparse point is not allowed in deployment path: {path}")


def _assert_plain_directory_ancestry(path: Path) -> None:
    current = path
    while True:
        _assert_plain(current, directory=True)
        if current.parent == current:
            return
        current = current.parent


def _create_plain_directory(path: Path) -> None:
    existing = path
    while not existing.exists():
        if existing.parent == existing:
            raise DeployError(f"cannot locate existing parent for directory: {path}")
        existing = existing.parent
    _assert_plain_directory_ancestry(existing)
    path.mkdir(parents=True, exist_ok=True)
    _assert_plain_directory_ancestry(path)


@contextmanager
def _exclusive_publish_lock(path: Path):
    _create_plain_directory(path.parent)
    if path.exists():
        _assert_plain(path, directory=False)
    handle = path.open("a+b")
    locked = False
    try:
        _assert_plain(path, directory=False)
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
            os.fsync(handle.fileno())
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise DeployError("another Results.lua publisher already holds the lock") from exc
        locked = True
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _require_not_running(state_query: Callable[[], WowState], *, phase: str) -> WowState:
    state = _state_value(state_query)
    if state is not WowState.NOT_RUNNING:
        raise DeployError(f"{phase} blocks installation: {state.value}")
    return state


def _unlink_if_confirmed_stopped(path: Path, state_query: Callable[[], WowState]) -> None:
    try:
        state = _state_value(state_query)
    except DeployError:
        return
    if state is WowState.NOT_RUNNING:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _verify_create_only_link_support(
    source: Path,
    interface: Path,
    state_query: Callable[[], WowState],
) -> None:
    probe = interface / f".lga-link-probe-{uuid.uuid4().hex}.tmp"
    try:
        _require_not_running(state_query, phase="hardlink-probe WoW preflight")
        os.link(source, probe)
        if probe.read_bytes() != source.read_bytes():
            raise DeployError("create-only publication probe failed readback")
    except OSError as exc:
        raise DeployError(f"create-only publication is unavailable: {exc}") from exc
    finally:
        if probe.exists():
            _unlink_if_confirmed_stopped(probe, state_query)


@contextmanager
def _stable_live_directories(
    retail: Path,
    interface: Path,
    addon_dir: Path,
    *,
    protected_files: tuple[Path, ...] = (),
):
    """Hold directory identities and deny writes/replaces of protected addon code."""
    if os.name != "nt":
        raise DeployError("live Results.lua publication is supported only on Windows")
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    handles = []
    try:
        for path in (retail, interface, interface / "AddOns", addon_dir):
            handle = create_file(
                str(path),
                0x80000000,  # GENERIC_READ
                0x00000001 | 0x00000002,  # share read/write, deliberately deny delete
                None,
                3,  # OPEN_EXISTING
                0x02000000,  # FILE_FLAG_BACKUP_SEMANTICS for directories
                None,
            )
            if handle == wintypes.HANDLE(-1).value:
                error = ctypes.get_last_error()
                raise DeployError(f"cannot lock live directory identity {path}: WinError {error}")
            handles.append(handle)
        for path in protected_files:
            _assert_plain(path, directory=False)
            handle = create_file(
                str(path),
                0x80000000,  # GENERIC_READ
                0x00000001,  # share read only; deny writes and delete/replace
                None,
                3,  # OPEN_EXISTING
                0x00000080,  # FILE_ATTRIBUTE_NORMAL
                None,
            )
            if handle == wintypes.HANDLE(-1).value:
                error = ctypes.get_last_error()
                raise DeployError(f"cannot lock live addon file {path}: WinError {error}")
            handles.append(handle)
        yield
    finally:
        for handle in reversed(handles):
            close_handle(handle)


def _validate_expected_code_files(expected_code_files: Mapping[str, bytes]) -> None:
    if set(expected_code_files) != set(CODE_FILE_NAMES):
        raise DeployError("expected addon code file set is incomplete or contains unknown files")


def _mismatched_code_files(target_dir: Path, expected_code_files: Mapping[str, bytes]) -> list[str]:
    return sorted(
        name
        for name, content in expected_code_files.items()
        if (target_dir / name).read_bytes() != content
    )


def _validate_target(
    addon_dir: Path, *, allow_missing_results_for_recovery: bool = False
) -> tuple[Path, Path, Path]:
    addon_dir = addon_dir.absolute()
    if addon_dir.name.casefold() != "localgearadvisor":
        raise DeployError("addon target must end in Interface/AddOns/LocalGearAdvisor")
    addons = addon_dir.parent
    interface = addons.parent
    if addons.name.casefold() != "addons" or interface.name.casefold() != "interface":
        raise DeployError("addon target must be under Interface/AddOns/LocalGearAdvisor")
    retail = interface.parent
    if retail.name.casefold() != "_retail_":
        raise DeployError("addon target must belong to a _retail_ installation")
    _assert_plain_directory_ancestry(addon_dir)
    names = {entry.name for entry in addon_dir.iterdir()}
    valid_inventories = {_EXPECTED_FILES}
    if allow_missing_results_for_recovery:
        valid_inventories.add(_EXPECTED_FILES - {"Results.lua"})
    if names not in valid_inventories or any(entry.is_dir() for entry in addon_dir.iterdir()):
        expected_names = sorted(_EXPECTED_FILES)
        raise DeployError(
            f"installed addon inventory mismatch: expected {expected_names}, got {sorted(names)}"
        )
    for name in names:
        _assert_plain(addon_dir / name, directory=False)
    return retail, interface, addon_dir


def _require_outside_tree(path: Path, tree: Path, *, label: str) -> None:
    resolved = path.absolute().resolve(strict=False)
    tree_resolved = tree.resolve(strict=True)
    try:
        resolved.relative_to(tree_resolved)
    except ValueError:
        return
    raise DeployError(f"{label} must be outside {tree}: {path}")


def _target_publish_lock_path(target: Path, retail: Path) -> Path:
    normalized = os.path.normcase(str(target.resolve(strict=False)))
    key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    lock = Path(tempfile.gettempdir()) / "LocalGearAdvisor" / "publish-locks" / f"{key}.lock"
    _require_outside_tree(lock, retail, label="target publication lock")
    return lock


def _saved_variables_inventory(retail: Path) -> dict[str, str]:
    wtf = retail / "WTF"
    if not wtf.exists():
        return {}
    _assert_plain(wtf, directory=True)
    inventory: dict[str, str] = {}
    for path in sorted(wtf.rglob("LocalGearAdvisor.lua*")):
        if path.is_file():
            current = path.parent
            while current != retail:
                _assert_plain(current, directory=True)
                current = current.parent
            _assert_plain(path, directory=False)
            inventory[path.relative_to(retail).as_posix()] = _digest(path)
    return inventory


def _state_value(state_query: Callable[[], WowState]) -> WowState:
    try:
        state = state_query()
    except Exception as exc:
        raise DeployError(f"WoW process state query failed: {exc}") from exc
    if not isinstance(state, WowState):
        raise DeployError(f"WoW process state query returned an invalid value: {state!r}")
    return state


def _write_fsynced_exclusive(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise DeployError(f"deployment destination already exists: {path}") from exc
    if _digest(path) != hashlib.sha256(data).hexdigest():
        raise DeployError(f"written file verification failed: {path}")


def _write_receipt_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        _write_fsynced_exclusive(temporary, content.encode("utf-8"))
        os.replace(temporary, path)
        if path.read_text(encoding="utf-8") != content:
            raise DeployError("deployment receipt readback verification failed")
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _inventory_summary(inventory: dict[str, str]) -> dict[str, object]:
    canonical = json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"count": len(inventory), "sha256": hashlib.sha256(canonical).hexdigest()}


def _recover_live_publication(
    *,
    pending: Path,
    target: Path,
    interface: Path,
    state_query: Callable[[], WowState],
) -> None:
    if not pending.exists():
        return
    try:
        payload = json.loads(pending.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeployError(f"live publication journal is malformed: {exc}") from exc
    keys = {"version", "target", "backup", "oldSha256", "stagedSha256"}
    if not isinstance(payload, dict) or set(payload) != keys or payload["version"] != 1:
        raise DeployError("live publication journal structure is invalid")
    if payload["target"] != str(target):
        raise DeployError("live publication journal target binding is invalid")
    old_hash = payload["oldSha256"]
    staged_hash = payload["stagedSha256"]
    if not isinstance(old_hash, str) or not _SHA256_RE.fullmatch(old_hash):
        raise DeployError("live publication journal old generation hash is invalid")
    if not isinstance(staged_hash, str) or not _SHA256_RE.fullmatch(staged_hash):
        raise DeployError("live publication journal staged generation hash is invalid")
    backup = Path(payload["backup"]) if isinstance(payload["backup"], str) else Path()
    _require_outside_tree(backup, interface / "AddOns", label="journal backup")
    _assert_plain_directory_ancestry(backup.parent)
    current_hash = _digest(target) if target.exists() else None
    if current_hash == staged_hash or current_hash == old_hash:
        pending.unlink()
        return
    if current_hash is not None:
        raise DeployError("live publication recovery refused a foreign Results.lua generation")
    if not backup.is_file() or _digest(backup) != old_hash:
        raise DeployError("live publication recovery cannot verify its backup")
    prepared = interface / f".lga-results-recovery-{uuid.uuid4().hex}.tmp"
    try:
        _require_not_running(state_query, phase="recovery prepared-file WoW preflight")
        _write_fsynced_exclusive(prepared, backup.read_bytes())
        _require_not_running(state_query, phase="recovery publish WoW preflight")
        os.link(prepared, target)
        if _digest(target) != old_hash:
            raise DeployError("live publication recovery readback failed")
    except FileExistsError as exc:
        raise DeployError("live publication recovery preserved a concurrent generation") from exc
    finally:
        if prepared.exists():
            _unlink_if_confirmed_stopped(prepared, state_query)
    pending.unlink()


def _publish_results_live_unlocked(
    *,
    staged_results: Path,
    canonical_state_path: Path,
    expected_staged_sha256: str,
    addon_dir: Path,
    expected_code_files: Mapping[str, bytes],
    receipt_path: Path,
    timestamp: str,
    state_query: Callable[[], WowState] = query_wow_state,
    backup_root: Path | None = None,
) -> DeployReceipt:
    if not _SHA256_RE.fullmatch(expected_staged_sha256):
        raise DeployError("expected staged Results.lua hash is not a lowercase SHA-256")
    if not _TIMESTAMP_RE.fullmatch(timestamp):
        raise DeployError("deployment timestamp must use YYYYMMDDTHHMMSSZ")
    _validate_expected_code_files(expected_code_files)
    _assert_plain(staged_results, directory=False)
    staged_bytes = staged_results.read_bytes()
    staged_hash = hashlib.sha256(staged_bytes).hexdigest()
    if staged_hash != expected_staged_sha256:
        raise DeployError("staged Results.lua changed after the completed analysis")
    _assert_plain(canonical_state_path, directory=False)
    try:
        canonical_bytes = render_aggregate_lua(load_state(canonical_state_path)).encode("utf-8")
    except Exception as exc:
        raise DeployError(f"canonical aggregate state is invalid: {exc}") from exc
    if staged_bytes != canonical_bytes:
        raise DeployError("staged Results.lua is not the canonical schemaVersion 2 projection")

    pending = receipt_path.with_name(receipt_path.name + ".pending.json")
    retail, interface, target_dir = _validate_target(
        addon_dir, allow_missing_results_for_recovery=pending.exists()
    )
    target = target_dir / "Results.lua"
    protected_files = tuple(target_dir / name for name in expected_code_files)
    mismatched = _mismatched_code_files(target_dir, expected_code_files)
    if mismatched:
        raise DeployError(
            "installed addon code is incompatible with this Results.lua schema: "
            + ", ".join(mismatched)
        )

    initial = _require_not_running(state_query, phase="WoW process state")

    backups = (backup_root or interface / "HermesBackups" / "LocalGearAdvisor").absolute()
    addons = interface / "AddOns"
    _require_outside_tree(backups, addons, label="Results.lua backup directory")
    if backups.anchor.casefold() != interface.anchor.casefold():
        raise DeployError("Results.lua backup directory must be on the WoW filesystem")
    _require_not_running(state_query, phase="backup-directory WoW preflight")
    _create_plain_directory(backups)
    with _stable_live_directories(retail, interface, target_dir, protected_files=protected_files):
        _validate_target(addon_dir, allow_missing_results_for_recovery=pending.exists())
        if _mismatched_code_files(target_dir, expected_code_files):
            raise DeployError("addon code changed before Results.lua recovery")
        _require_not_running(state_query, phase="recovery WoW preflight")
        _recover_live_publication(
            pending=pending,
            target=target,
            interface=interface,
            state_query=state_query,
        )
        _validate_target(addon_dir)

    old_bytes = target.read_bytes()
    old_hash = hashlib.sha256(old_bytes).hexdigest()
    saved_before = _saved_variables_inventory(retail)
    backup = backups / f"Results-{timestamp}-{old_hash[:12]}.lua"
    if backup.exists():
        raise DeployError(f"deployment backup already exists: {backup}")

    prepared = interface / f".lga-results-{uuid.uuid4().hex}.tmp"
    published = False
    try:
        _require_not_running(state_query, phase="prepared-file WoW preflight")
        _write_fsynced_exclusive(prepared, staged_bytes)
        _verify_create_only_link_support(prepared, interface, state_query)
        if _mismatched_code_files(target_dir, expected_code_files):
            raise DeployError("addon code changed before Results.lua installation")
        if _saved_variables_inventory(retail) != saved_before:
            raise DeployError("SavedVariables changed before Results.lua installation")

        with _stable_live_directories(
            retail, interface, target_dir, protected_files=protected_files
        ):
            _validate_target(addon_dir)
            if _mismatched_code_files(target_dir, expected_code_files):
                raise DeployError("addon code changed before final Results.lua installation")
            final = _require_not_running(state_query, phase="final WoW preflight")
            payload = {
                "version": 1,
                "target": str(target),
                "backup": str(backup),
                "oldSha256": old_hash,
                "stagedSha256": staged_hash,
            }
            _write_receipt_atomic(
                pending, json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
            )
            _require_not_running(state_query, phase="rename WoW preflight")
            target.rename(backup)
            displaced_hash = _digest(backup)
            if displaced_hash != old_hash:
                payload["oldSha256"] = displaced_hash
                _write_receipt_atomic(
                    pending,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
                )
                try:
                    _require_not_running(state_query, phase="foreign-generation recovery preflight")
                    os.link(backup, target)
                except FileExistsError:
                    pass
                if target.exists():
                    pending.unlink()
                raise DeployError(
                    "Results.lua changed immediately before publication; "
                    "foreign generation preserved"
                )
            try:
                _require_not_running(state_query, phase="publish WoW preflight")
                os.link(prepared, target)
            except FileExistsError as exc:
                pending.unlink()
                raise DeployError(
                    "concurrent Results.lua generation won publication and was preserved"
                ) from exc
            except OSError:
                rollback_state = _state_value(state_query)
                if rollback_state is WowState.NOT_RUNNING and not target.exists():
                    os.link(backup, target)
                    pending.unlink()
                raise
            published = True
            if _digest(target) != staged_hash:
                raise DeployError("installed Results.lua verification failed")
            pending.unlink()

        if _mismatched_code_files(target_dir, expected_code_files):
            raise DeployError("addon code changed during Results.lua installation")
        saved_after = _saved_variables_inventory(retail)
        if saved_after != saved_before:
            raise DeployError("SavedVariables changed during Results.lua installation")
        after = _state_value(state_query)
        if after is not WowState.NOT_RUNNING:
            raise DeployError(
                "WoW started during/after installation; installed hash is valid and retained"
            )
        receipt_payload = {
            "addonDir": str(target_dir),
            "backup": str(backup),
            "installedAtUtc": timestamp,
            "resultsSha256": staged_hash,
            "savedVariablesBefore": _inventory_summary(saved_before),
            "savedVariablesAfter": _inventory_summary(saved_after),
            "wowStateAfter": after.value,
            "wowStateFinalPreflight": final.value,
            "wowStateInitial": initial.value,
        }
        _write_receipt_atomic(
            receipt_path,
            json.dumps(receipt_payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        return DeployReceipt(
            results_sha256=staged_hash,
            backup=backup.resolve(),
            receipt=receipt_path.resolve(),
            addon_dir=target_dir.resolve(),
        )
    except Exception as exc:
        if published:
            raise DeployError(
                "deployment published a validated Results.lua but a post-publication step "
                f"failed; the new generation was retained to avoid overwriting concurrent data "
                f"(backup: {backup}): {exc}"
            ) from exc
        if isinstance(exc, DeployError):
            raise
        raise DeployError(f"Results.lua deployment failed: {exc}") from exc
    finally:
        if prepared.exists():
            _unlink_if_confirmed_stopped(prepared, state_query)


def publish_results_live(
    *,
    staged_results: Path,
    canonical_state_path: Path,
    expected_staged_sha256: str,
    addon_dir: Path,
    expected_code_files: Mapping[str, bytes],
    receipt_path: Path,
    timestamp: str,
    state_query: Callable[[], WowState] = query_wow_state,
    backup_root: Path | None = None,
) -> DeployReceipt:
    if not _SHA256_RE.fullmatch(expected_staged_sha256):
        raise DeployError("expected staged Results.lua hash is not a lowercase SHA-256")
    if not _TIMESTAMP_RE.fullmatch(timestamp):
        raise DeployError("deployment timestamp must use YYYYMMDDTHHMMSSZ")
    _validate_expected_code_files(expected_code_files)
    pending = receipt_path.with_name(receipt_path.name + ".pending.json")
    retail, interface, target_dir = _validate_target(
        addon_dir, allow_missing_results_for_recovery=pending.exists()
    )
    external_paths = {
        staged_results.absolute(),
        canonical_state_path.absolute(),
        receipt_path.absolute(),
    }
    if len(external_paths) != 3:
        raise DeployError("staging, canonical state and receipt paths must be distinct")
    addons = interface / "AddOns"
    _require_outside_tree(staged_results, addons, label="staged Results.lua")
    _require_outside_tree(canonical_state_path, addons, label="canonical aggregate state")
    _require_outside_tree(receipt_path, retail, label="deployment receipt")
    if staged_results.absolute() == receipt_path.absolute():
        raise DeployError("deployment receipt must not replace the staged Results.lua")
    initial = _state_value(state_query)
    if initial is not WowState.NOT_RUNNING:
        raise DeployError(f"WoW process state blocks installation: {initial.value}")

    lock = _target_publish_lock_path(target_dir / "Results.lua", retail)
    with _exclusive_publish_lock(lock):
        return _publish_results_live_unlocked(
            staged_results=staged_results,
            canonical_state_path=canonical_state_path,
            expected_staged_sha256=expected_staged_sha256,
            addon_dir=addon_dir,
            expected_code_files=expected_code_files,
            receipt_path=receipt_path,
            timestamp=timestamp,
            state_query=state_query,
            backup_root=backup_root,
        )
