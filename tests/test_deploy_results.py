from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from local_gear_advisor.deploy_results import DeployError, publish_results_live
from local_gear_advisor.safety import WowState
from local_gear_advisor.state import empty_state, render_aggregate_lua, save_state

CORE = b"core-schema-v2\n"
TOC = (
    b"## Interface: 120007\nResults.lua\nLocalization.lua\nSha256.lua\n"
    b"Core.lua\nImport.lua\nMinimap.lua\nUI.lua\n"
)
LOCALIZATION = b"localization-schema-v2\n"
SHA256 = b"sha256-schema-v2\n"
IMPORT = b"import-schema-v2\n"
MINIMAP = b"minimap-schema-v2\n"
UI = b"ui-schema-v2\n"
EXPECTED_CODE_FILES = {
    "LocalGearAdvisor.toc": TOC,
    "Localization.lua": LOCALIZATION,
    "Sha256.lua": SHA256,
    "Core.lua": CORE,
    "Import.lua": IMPORT,
    "Minimap.lua": MINIMAP,
    "UI.lua": UI,
}
OLD_RESULTS = b"LocalGearAdvisorResults = { schemaVersion = 2, profiles = {} }\n"
NEW_RESULTS = render_aggregate_lua(empty_state()).encode("utf-8")


def _tree(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    retail = tmp_path / "World of Warcraft" / "_retail_"
    addon = retail / "Interface" / "AddOns" / "LocalGearAdvisor"
    addon.mkdir(parents=True)
    for name, content in EXPECTED_CODE_FILES.items():
        (addon / name).write_bytes(content)
    (addon / "Results.lua").write_bytes(OLD_RESULTS)
    saved = retail / "WTF" / "Account" / "A" / "SavedVariables" / "LocalGearAdvisor.lua"
    saved.parent.mkdir(parents=True)
    saved.write_bytes(b"saved\n")
    staged = tmp_path / "staging" / "Results.lua"
    staged.parent.mkdir()
    staged.write_bytes(NEW_RESULTS)
    save_state(staged.parent / "profiles.json", empty_state())
    receipt = tmp_path / "state" / "deploy-receipt.json"
    return addon, staged, receipt, saved


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_publish_results_live_replaces_only_results_and_preserves_saved_variables(
    tmp_path: Path,
) -> None:
    addon, staged, receipt, saved = _tree(tmp_path)
    result = publish_results_live(
        staged_results=staged,
        canonical_state_path=staged.parent / "profiles.json",
        expected_staged_sha256=_sha(NEW_RESULTS),
        addon_dir=addon,
        expected_code_files=EXPECTED_CODE_FILES,
        receipt_path=receipt,
        state_query=lambda: WowState.NOT_RUNNING,
        timestamp="20260801T200000Z",
    )

    assert (addon / "Results.lua").read_bytes() == NEW_RESULTS
    for name, content in EXPECTED_CODE_FILES.items():
        assert (addon / name).read_bytes() == content
    assert saved.read_bytes() == b"saved\n"
    assert result.results_sha256 == _sha(NEW_RESULTS)
    assert result.backup.read_bytes() == OLD_RESULTS
    assert result.receipt == receipt
    assert receipt.is_file()
    receipt_data = json.loads(receipt.read_text(encoding="utf-8"))
    assert receipt_data["savedVariablesBefore"]["count"] == 1
    assert set(receipt_data["savedVariablesBefore"]) == {"count", "sha256"}
    assert "Account" not in receipt.read_text(encoding="utf-8")


@pytest.mark.parametrize("state", [WowState.RUNNING, WowState.UNKNOWN])
def test_publish_results_live_blocks_before_writes_when_wow_not_proven_closed(
    tmp_path: Path, state: WowState
) -> None:
    addon, staged, receipt, _ = _tree(tmp_path)

    with pytest.raises(DeployError, match="blocks"):
        publish_results_live(
            staged_results=staged,
            canonical_state_path=staged.parent / "profiles.json",
            expected_staged_sha256=_sha(NEW_RESULTS),
            addon_dir=addon,
            expected_code_files=EXPECTED_CODE_FILES,
            receipt_path=receipt,
            state_query=lambda: state,
            timestamp="20260801T200000Z",
        )

    assert (addon / "Results.lua").read_bytes() == OLD_RESULTS
    assert not receipt.exists()


@pytest.mark.parametrize("state", [WowState.RUNNING, WowState.UNKNOWN])
def test_publish_results_live_blocks_before_live_tree_writes_if_wow_starts_after_lock(
    tmp_path: Path, state: WowState
) -> None:
    addon, staged, receipt, _ = _tree(tmp_path)
    states = iter((WowState.NOT_RUNNING, WowState.NOT_RUNNING, state))

    with pytest.raises(DeployError, match="blocks"):
        publish_results_live(
            staged_results=staged,
            canonical_state_path=staged.parent / "profiles.json",
            expected_staged_sha256=_sha(NEW_RESULTS),
            addon_dir=addon,
            expected_code_files=EXPECTED_CODE_FILES,
            receipt_path=receipt,
            state_query=lambda: next(states),
            timestamp="20260801T200000Z",
        )

    assert (addon / "Results.lua").read_bytes() == OLD_RESULTS
    assert not receipt.exists()
    assert not (addon.parent.parent / "HermesBackups").exists()


@pytest.mark.parametrize("state", [WowState.RUNNING, WowState.UNKNOWN])
def test_publish_results_live_never_rolls_back_after_unsafe_postcheck(
    tmp_path: Path, state: WowState
) -> None:
    addon, staged, receipt, _ = _tree(tmp_path)
    states = iter(([WowState.NOT_RUNNING] * 10) + [state])

    with pytest.raises(DeployError, match="retained"):
        publish_results_live(
            staged_results=staged,
            canonical_state_path=staged.parent / "profiles.json",
            expected_staged_sha256=_sha(NEW_RESULTS),
            addon_dir=addon,
            expected_code_files=EXPECTED_CODE_FILES,
            receipt_path=receipt,
            state_query=lambda: next(states),
            timestamp="20260801T200000Z",
        )

    assert (addon / "Results.lua").read_bytes() == NEW_RESULTS
    assert not receipt.exists()


def test_publish_results_live_rejects_changed_staging_and_incompatible_core(tmp_path: Path) -> None:
    addon, staged, receipt, _ = _tree(tmp_path)

    with pytest.raises(DeployError, match="staged Results.lua changed"):
        publish_results_live(
            staged_results=staged,
            canonical_state_path=staged.parent / "profiles.json",
            expected_staged_sha256="0" * 64,
            addon_dir=addon,
            expected_code_files=EXPECTED_CODE_FILES,
            receipt_path=receipt,
            state_query=lambda: WowState.NOT_RUNNING,
            timestamp="20260801T200000Z",
        )

    (addon / "Core.lua").write_bytes(b"old core\n")
    with pytest.raises(DeployError, match="Core.lua"):
        publish_results_live(
            staged_results=staged,
            canonical_state_path=staged.parent / "profiles.json",
            expected_staged_sha256=_sha(NEW_RESULTS),
            addon_dir=addon,
            expected_code_files=EXPECTED_CODE_FILES,
            receipt_path=receipt,
            state_query=lambda: WowState.NOT_RUNNING,
            timestamp="20260801T200000Z",
        )

    assert (addon / "Results.lua").read_bytes() == OLD_RESULTS


@pytest.mark.parametrize(
    "name", ["Localization.lua", "Sha256.lua", "Import.lua", "Minimap.lua", "UI.lua"]
)
def test_publish_results_live_rejects_when_any_new_code_file_is_incompatible(
    tmp_path: Path, name: str
) -> None:
    addon, staged, receipt, _ = _tree(tmp_path)
    (addon / name).write_bytes(b"tampered\n")

    with pytest.raises(DeployError, match=name):
        publish_results_live(
            staged_results=staged,
            canonical_state_path=staged.parent / "profiles.json",
            expected_staged_sha256=_sha(NEW_RESULTS),
            addon_dir=addon,
            expected_code_files=EXPECTED_CODE_FILES,
            receipt_path=receipt,
            state_query=lambda: WowState.NOT_RUNNING,
            timestamp="20260801T200000Z",
        )

    assert (addon / "Results.lua").read_bytes() == OLD_RESULTS


def test_expected_addon_assets_matches_the_repository_source_bytewise() -> None:
    from local_gear_advisor.deploy_results import CODE_FILE_NAMES, expected_addon_assets

    source = Path(__file__).parents[1] / "addon" / "LocalGearAdvisor"
    assets = expected_addon_assets()

    assert set(assets) == set(CODE_FILE_NAMES)
    for name, content in assets.items():
        assert content == (source / name).read_bytes()


def test_extract_addon_template_creates_complete_byte_exact_fresh_staging(tmp_path: Path) -> None:
    from local_gear_advisor.deploy_results import extract_addon_template

    source = Path(__file__).parents[1] / "addon" / "LocalGearAdvisor"
    destination = tmp_path / "LocalGearAdvisor"

    assert extract_addon_template(destination) == destination
    assert {path.name for path in destination.iterdir()} == {
        path.name for path in source.iterdir() if path.is_file()
    }
    for path in destination.iterdir():
        assert path.read_bytes() == (source / path.name).read_bytes()


def test_extract_addon_template_refuses_an_existing_destination(tmp_path: Path) -> None:
    from local_gear_advisor.deploy_results import extract_addon_template

    destination = tmp_path / "LocalGearAdvisor"
    destination.mkdir()

    with pytest.raises(DeployError, match="already exists"):
        extract_addon_template(destination)


def test_extract_addon_template_never_deletes_a_racing_foreign_destination(
    tmp_path: Path, monkeypatch
) -> None:
    from local_gear_advisor.deploy_results import extract_addon_template

    destination = tmp_path / "LocalGearAdvisor"

    def racing_rename(source, target) -> None:
        assert Path(target) == destination
        destination.mkdir()
        (destination / "foreign.txt").write_text("foreign", encoding="utf-8")
        raise FileExistsError("racing foreign directory")

    monkeypatch.setattr(os, "rename", racing_rename)

    with pytest.raises(FileExistsError, match="racing foreign"):
        extract_addon_template(destination)

    assert (destination / "foreign.txt").read_text(encoding="utf-8") == "foreign"


def test_extract_addon_template_never_reports_success_for_a_swapped_source_generation(
    tmp_path: Path, monkeypatch
) -> None:
    from local_gear_advisor.deploy_results import extract_addon_template

    destination = tmp_path / "LocalGearAdvisor"
    real_rename = os.rename

    def swapped_source_rename(source, target) -> None:
        source = Path(source)
        checked_generation = source.with_name(source.name + "-checked")
        real_rename(source, checked_generation)
        source.mkdir()
        (source / "foreign.txt").write_text("foreign", encoding="utf-8")
        real_rename(source, target)

    monkeypatch.setattr(os, "rename", swapped_source_rename)

    with pytest.raises(DeployError, match="published addon failed byte-for-byte readback"):
        extract_addon_template(destination)

    assert {path.name for path in destination.iterdir()} == {"foreign.txt"}


def test_extract_addon_template_retains_private_generation_on_write_failure(
    tmp_path: Path, monkeypatch
) -> None:
    from local_gear_advisor.deploy_results import extract_addon_template

    destination = tmp_path / "LocalGearAdvisor"
    real_open = Path.open

    def failing_open(path: Path, *args, **kwargs):
        if path.name == "Core.lua" and ".LocalGearAdvisor.staging-" in path.parent.name:
            raise OSError("injected write failure")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)

    with pytest.raises(OSError, match="injected write failure"):
        extract_addon_template(destination)

    assert destination.exists() is False
    quarantined = list(tmp_path.glob(".LocalGearAdvisor.staging-*"))
    assert len(quarantined) == 1
    assert quarantined[0].is_dir()


def test_publish_results_live_rejects_incomplete_expected_code_files(tmp_path: Path) -> None:
    addon, staged, receipt, _ = _tree(tmp_path)
    incomplete = {"Core.lua": CORE, "LocalGearAdvisor.toc": TOC}

    with pytest.raises(DeployError, match="expected addon code file set"):
        publish_results_live(
            staged_results=staged,
            canonical_state_path=staged.parent / "profiles.json",
            expected_staged_sha256=_sha(NEW_RESULTS),
            addon_dir=addon,
            expected_code_files=incomplete,
            receipt_path=receipt,
            state_query=lambda: WowState.NOT_RUNNING,
            timestamp="20260801T200000Z",
        )

    assert (addon / "Results.lua").read_bytes() == OLD_RESULTS


def test_publish_results_live_rejects_backup_inside_addons(tmp_path: Path) -> None:
    addon, staged, receipt, _ = _tree(tmp_path)

    with pytest.raises(DeployError, match="must be outside"):
        publish_results_live(
            staged_results=staged,
            canonical_state_path=staged.parent / "profiles.json",
            expected_staged_sha256=_sha(NEW_RESULTS),
            addon_dir=addon,
            expected_code_files=EXPECTED_CODE_FILES,
            receipt_path=receipt,
            state_query=lambda: WowState.NOT_RUNNING,
            backup_root=addon.parent / "unsafe-backups",
            timestamp="20260801T200000Z",
        )

    assert (addon / "Results.lua").read_bytes() == OLD_RESULTS


def test_receipt_is_rejected_anywhere_inside_live_retail_tree(tmp_path: Path) -> None:
    addon, staged, _, _ = _tree(tmp_path)
    receipt = addon.parent.parent / "HermesReceipts" / "receipt.json"
    with pytest.raises(DeployError, match="deployment receipt must be outside"):
        publish_results_live(
            staged_results=staged,
            canonical_state_path=staged.parent / "profiles.json",
            expected_staged_sha256=_sha(NEW_RESULTS),
            addon_dir=addon,
            expected_code_files=EXPECTED_CODE_FILES,
            receipt_path=receipt,
            state_query=lambda: WowState.NOT_RUNNING,
            timestamp="20260801T200000Z",
        )
    assert not receipt.parent.exists()
    assert (addon / "Results.lua").read_bytes() == OLD_RESULTS


def test_publish_results_live_rolls_back_results_after_failed_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    addon, staged, receipt, _ = _tree(tmp_path)
    import local_gear_advisor.deploy_results as deploy

    real_digest = deploy._digest
    target = addon / "Results.lua"
    calls = 0

    def corrupt_post_readback(path: Path) -> str:
        nonlocal calls
        if path == target:
            calls += 1
            if calls == 1:
                return "f" * 64
        return real_digest(path)

    monkeypatch.setattr(deploy, "_digest", corrupt_post_readback)

    with pytest.raises(DeployError, match="verification"):
        publish_results_live(
            staged_results=staged,
            canonical_state_path=staged.parent / "profiles.json",
            expected_staged_sha256=_sha(NEW_RESULTS),
            addon_dir=addon,
            expected_code_files=EXPECTED_CODE_FILES,
            receipt_path=receipt,
            state_query=lambda: WowState.NOT_RUNNING,
            timestamp="20260801T200000Z",
        )

    assert (addon / "Results.lua").read_bytes() == NEW_RESULTS
    assert not receipt.exists()


def test_publish_results_live_never_rolls_back_over_a_foreign_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    addon, staged, receipt, _ = _tree(tmp_path)
    import local_gear_advisor.deploy_results as deploy

    foreign = b"foreign newer Results.lua\n"

    real_write_receipt = deploy._write_receipt_atomic

    def fail_receipt(path: Path, content: str) -> None:
        if path == receipt:
            (addon / "Results.lua").write_bytes(foreign)
            raise OSError("receipt failure after foreign replacement")
        real_write_receipt(path, content)

    monkeypatch.setattr(deploy, "_write_receipt_atomic", fail_receipt)

    with pytest.raises(DeployError, match="retained"):
        publish_results_live(
            staged_results=staged,
            canonical_state_path=staged.parent / "profiles.json",
            expected_staged_sha256=_sha(NEW_RESULTS),
            addon_dir=addon,
            expected_code_files=EXPECTED_CODE_FILES,
            receipt_path=receipt,
            state_query=lambda: WowState.NOT_RUNNING,
            timestamp="20260801T200000Z",
        )

    assert (addon / "Results.lua").read_bytes() == foreign


def test_publish_results_live_rejects_concurrent_publisher(tmp_path: Path) -> None:
    addon, staged, receipt, _ = _tree(tmp_path)
    import local_gear_advisor.deploy_results as deploy

    second_receipt = receipt.with_name("other-receipt.json")
    lock = deploy._target_publish_lock_path(addon / "Results.lua", addon.parents[2])
    with deploy._exclusive_publish_lock(lock):
        with pytest.raises(DeployError, match="already holds the lock"):
            publish_results_live(
                staged_results=staged,
                canonical_state_path=staged.parent / "profiles.json",
                expected_staged_sha256=_sha(NEW_RESULTS),
                addon_dir=addon,
                expected_code_files=EXPECTED_CODE_FILES,
                receipt_path=second_receipt,
                state_query=lambda: WowState.NOT_RUNNING,
                timestamp="20260801T200000Z",
            )

    assert (addon / "Results.lua").read_bytes() == OLD_RESULTS
    assert not receipt.exists()
    assert not second_receipt.exists()


def test_different_receipts_cannot_bypass_target_publication_lock(tmp_path: Path) -> None:
    addon, staged, receipt, _ = _tree(tmp_path)
    second_receipt = receipt.with_name("other-receipt.json")
    calls = 0
    second_blocked = False

    def state_query() -> WowState:
        nonlocal calls, second_blocked
        calls += 1
        if calls == 4:
            try:
                publish_results_live(
                    staged_results=staged,
                    canonical_state_path=staged.parent / "profiles.json",
                    expected_staged_sha256=_sha(NEW_RESULTS),
                    addon_dir=addon,
                    expected_code_files=EXPECTED_CODE_FILES,
                    receipt_path=second_receipt,
                    state_query=lambda: WowState.NOT_RUNNING,
                    timestamp="20260801T200001Z",
                )
            except DeployError as exc:
                second_blocked = "already holds the lock" in str(exc)
        return WowState.NOT_RUNNING

    publish_results_live(
        staged_results=staged,
        canonical_state_path=staged.parent / "profiles.json",
        expected_staged_sha256=_sha(NEW_RESULTS),
        addon_dir=addon,
        expected_code_files=EXPECTED_CODE_FILES,
        receipt_path=receipt,
        state_query=state_query,
        timestamp="20260801T200000Z",
    )

    assert second_blocked
    assert receipt.is_file()
    assert not second_receipt.exists()
    assert (addon / "Results.lua").read_bytes() == NEW_RESULTS
    backups = addon.parent.parent / "HermesBackups" / "LocalGearAdvisor"
    assert len(list(backups.glob("Results-*.lua"))) == 1


def test_publish_results_live_replace_failure_preserves_old_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    addon, staged, receipt, _ = _tree(tmp_path)
    import local_gear_advisor.deploy_results as deploy

    real_link = deploy.os.link
    target = addon / "Results.lua"

    def fail_target_link(source: Path, destination: Path) -> None:
        if Path(destination) == target and Path(source).name.startswith(".lga-results-"):
            raise OSError("simulated create-only publication failure")
        real_link(source, destination)

    monkeypatch.setattr(deploy.os, "link", fail_target_link)

    with pytest.raises(DeployError, match="create-only publication failure"):
        publish_results_live(
            staged_results=staged,
            canonical_state_path=staged.parent / "profiles.json",
            expected_staged_sha256=_sha(NEW_RESULTS),
            addon_dir=addon,
            expected_code_files=EXPECTED_CODE_FILES,
            receipt_path=receipt,
            state_query=lambda: WowState.NOT_RUNNING,
            timestamp="20260801T200000Z",
        )

    assert target.read_bytes() == OLD_RESULTS
    assert not receipt.exists()


def test_foreign_generation_written_during_final_preflight_is_preserved(tmp_path: Path) -> None:
    addon, staged, receipt, _ = _tree(tmp_path)
    target = addon / "Results.lua"
    foreign = b"foreign generation during final preflight\n"
    calls = 0

    def state_query() -> WowState:
        nonlocal calls
        calls += 1
        if calls == 8:
            target.write_bytes(foreign)
        return WowState.NOT_RUNNING

    with pytest.raises(DeployError, match="foreign generation preserved"):
        publish_results_live(
            staged_results=staged,
            canonical_state_path=staged.parent / "profiles.json",
            expected_staged_sha256=_sha(NEW_RESULTS),
            addon_dir=addon,
            expected_code_files=EXPECTED_CODE_FILES,
            receipt_path=receipt,
            state_query=state_query,
            timestamp="20260801T200001Z",
        )
    assert target.read_bytes() == foreign


def test_live_directory_identity_is_held_through_final_publication(tmp_path: Path) -> None:
    addon, staged, receipt, _ = _tree(tmp_path)
    calls = 0
    rename_blocked = False

    def state_query() -> WowState:
        nonlocal calls, rename_blocked
        calls += 1
        if calls == 4:
            try:
                addon.rename(addon.with_name("swapped"))
            except PermissionError:
                rename_blocked = True
        return WowState.NOT_RUNNING

    publish_results_live(
        staged_results=staged,
        canonical_state_path=staged.parent / "profiles.json",
        expected_staged_sha256=_sha(NEW_RESULTS),
        addon_dir=addon,
        expected_code_files=EXPECTED_CODE_FILES,
        receipt_path=receipt,
        state_query=state_query,
        timestamp="20260801T200002Z",
    )
    assert rename_blocked
    assert (addon / "Results.lua").read_bytes() == NEW_RESULTS


def test_core_and_toc_are_write_locked_through_final_publication(tmp_path: Path) -> None:
    addon, staged, receipt, _ = _tree(tmp_path)
    core = addon / "Core.lua"
    calls = 0
    write_blocked = False

    def state_query() -> WowState:
        nonlocal calls, write_blocked
        calls += 1
        if calls == 8:
            try:
                core.write_bytes(b"incompatible Core.lua\n")
            except PermissionError:
                write_blocked = True
        return WowState.NOT_RUNNING

    publish_results_live(
        staged_results=staged,
        canonical_state_path=staged.parent / "profiles.json",
        expected_staged_sha256=_sha(NEW_RESULTS),
        addon_dir=addon,
        expected_code_files=EXPECTED_CODE_FILES,
        receipt_path=receipt,
        state_query=state_query,
        timestamp="20260801T200002Z",
    )
    assert write_blocked
    assert core.read_bytes() == CORE
    assert (addon / "Results.lua").read_bytes() == NEW_RESULTS


def test_interrupted_live_publication_is_recovered_before_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    addon, staged, receipt, _ = _tree(tmp_path)
    import local_gear_advisor.deploy_results as deploy

    real_link = deploy.os.link
    interrupted = False

    def interrupt_first_publish(source: Path, destination: Path) -> None:
        nonlocal interrupted
        if not interrupted and Path(destination) == addon / "Results.lua":
            interrupted = True
            raise KeyboardInterrupt("simulated process interruption")
        real_link(source, destination)

    monkeypatch.setattr(deploy.os, "link", interrupt_first_publish)
    with pytest.raises(KeyboardInterrupt):
        publish_results_live(
            staged_results=staged,
            canonical_state_path=staged.parent / "profiles.json",
            expected_staged_sha256=_sha(NEW_RESULTS),
            addon_dir=addon,
            expected_code_files=EXPECTED_CODE_FILES,
            receipt_path=receipt,
            state_query=lambda: WowState.NOT_RUNNING,
            timestamp="20260801T200003Z",
        )
    assert not (addon / "Results.lua").exists()
    pending = receipt.with_name(receipt.name + ".pending.json")
    assert pending.is_file()

    recovery_states = iter(([WowState.NOT_RUNNING] * 5) + [WowState.RUNNING])
    with pytest.raises(DeployError, match="recovery publish WoW preflight"):
        publish_results_live(
            staged_results=staged,
            canonical_state_path=staged.parent / "profiles.json",
            expected_staged_sha256=_sha(NEW_RESULTS),
            addon_dir=addon,
            expected_code_files=EXPECTED_CODE_FILES,
            receipt_path=receipt,
            state_query=lambda: next(recovery_states),
            timestamp="20260801T200004Z",
        )
    assert not (addon / "Results.lua").exists()
    assert pending.is_file()

    blocked_states = iter((WowState.NOT_RUNNING, WowState.NOT_RUNNING, WowState.RUNNING))
    with pytest.raises(DeployError, match="backup-directory WoW preflight"):
        publish_results_live(
            staged_results=staged,
            canonical_state_path=staged.parent / "profiles.json",
            expected_staged_sha256=_sha(NEW_RESULTS),
            addon_dir=addon,
            expected_code_files=EXPECTED_CODE_FILES,
            receipt_path=receipt,
            state_query=lambda: next(blocked_states),
            timestamp="20260801T200004Z",
        )
    assert not (addon / "Results.lua").exists()
    assert pending.is_file()

    publish_results_live(
        staged_results=staged,
        canonical_state_path=staged.parent / "profiles.json",
        expected_staged_sha256=_sha(NEW_RESULTS),
        addon_dir=addon,
        expected_code_files=EXPECTED_CODE_FILES,
        receipt_path=receipt,
        state_query=lambda: WowState.NOT_RUNNING,
        timestamp="20260801T200004Z",
    )
    assert (addon / "Results.lua").read_bytes() == NEW_RESULTS
    assert not receipt.with_name(receipt.name + ".pending.json").exists()


def test_unavailable_hardlinks_fail_before_target_or_backup_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    addon, staged, receipt, _ = _tree(tmp_path)
    import local_gear_advisor.deploy_results as deploy

    monkeypatch.setattr(
        deploy.os,
        "link",
        lambda *_args: (_ for _ in ()).throw(OSError("hardlinks unavailable")),
    )
    with pytest.raises(DeployError, match="create-only publication is unavailable"):
        publish_results_live(
            staged_results=staged,
            canonical_state_path=staged.parent / "profiles.json",
            expected_staged_sha256=_sha(NEW_RESULTS),
            addon_dir=addon,
            expected_code_files=EXPECTED_CODE_FILES,
            receipt_path=receipt,
            state_query=lambda: WowState.NOT_RUNNING,
            timestamp="20260801T200005Z",
        )
    assert (addon / "Results.lua").read_bytes() == OLD_RESULTS
    backups = addon.parent.parent / "HermesBackups" / "LocalGearAdvisor"
    assert list(backups.glob("Results-*.lua")) == []


def test_noncanonical_staged_lua_is_rejected_even_with_matching_hash(tmp_path: Path) -> None:
    addon, staged, receipt, _ = _tree(tmp_path)
    malicious = b"schemaVersion = 2\nos.execute('not declarative')\n"
    staged.write_bytes(malicious)
    with pytest.raises(DeployError, match="canonical schemaVersion 2 projection"):
        publish_results_live(
            staged_results=staged,
            canonical_state_path=staged.parent / "profiles.json",
            expected_staged_sha256=_sha(malicious),
            addon_dir=addon,
            expected_code_files=EXPECTED_CODE_FILES,
            receipt_path=receipt,
            state_query=lambda: WowState.NOT_RUNNING,
            timestamp="20260801T200005Z",
        )
    assert (addon / "Results.lua").read_bytes() == OLD_RESULTS


def test_publish_results_live_retains_new_generation_if_receipt_and_backup_are_tampered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    addon, staged, receipt, _ = _tree(tmp_path)
    import local_gear_advisor.deploy_results as deploy

    real_write_receipt = deploy._write_receipt_atomic

    def tamper_backup_then_fail(path: Path, content: str) -> None:
        if path == receipt:
            backups = addon.parent.parent / "HermesBackups" / "LocalGearAdvisor"
            backup = next(backups.glob("Results-*.lua"))
            backup.write_bytes(b"tampered backup\n")
            raise OSError("receipt failure after backup tamper")
        real_write_receipt(path, content)

    monkeypatch.setattr(deploy, "_write_receipt_atomic", tamper_backup_then_fail)

    with pytest.raises(DeployError, match="retained"):
        publish_results_live(
            staged_results=staged,
            canonical_state_path=staged.parent / "profiles.json",
            expected_staged_sha256=_sha(NEW_RESULTS),
            addon_dir=addon,
            expected_code_files=EXPECTED_CODE_FILES,
            receipt_path=receipt,
            state_query=lambda: WowState.NOT_RUNNING,
            timestamp="20260801T200000Z",
        )

    assert (addon / "Results.lua").read_bytes() == NEW_RESULTS
    assert not receipt.exists()
