"""Behavioral proof (real Lua 5.1 execution via lupa, generic widget mock)
of the Profiles page: the merged fallback+imported list renders with the
correct source label and only offers Delete for imported (DB) profiles,
Details shows/hides the exact selected row's data, Delete requires a second
confirming click (and can be cancelled), deleting the currently-selected
profile closes its details panel, and Undo restores the last apply/delete
and refreshes the list -- all driven through the addon's real button
OnClick handlers, never through internal state directly.
"""

from __future__ import annotations

from _lua_ui_mock import UIHarness

from local_gear_advisor.import_codec import encode_profile_transport
from local_gear_advisor.state import (
    ProfileItem,
    ProfileRecord,
    empty_state,
    merge_profile,
    normalize_identity,
    render_aggregate_lua,
)

_BASELINE_SLOTS = (
    "head",
    "neck",
    "shoulder",
    "back",
    "chest",
    "wrist",
    "hands",
    "waist",
    "legs",
    "feet",
    "finger1",
    "finger2",
    "trinket1",
    "trinket2",
    "main_hand",
    "off_hand",
)


def _record(
    *,
    region: str = "eu",
    realm: str = "ExampleRealm",
    name: str = "Testchar",
    spec_id: int = 262,
    delta_percent: float = 2.345678,
) -> ProfileRecord:
    baseline_gear = {slot: None for slot in _BASELINE_SLOTS}
    return ProfileRecord(
        identity=normalize_identity(region=region, realm=realm, name=name, spec_id=spec_id),
        character_class="shaman",
        spec="elemental",
        level=90,
        race="orc",
        talents="CYQA...",
        trait_systems={"omnium_talents": "100:1/200:1"},
        baseline_gear=baseline_gear,
        fight_style="Patchwerk",
        baseline_dps=123456.789,
        simc_version="1205-01",
        simc_revision="5a982a3",
        game_version="12.0.7.68887",
        dbc_source="Live",
        profile_hash="a" * 64,
        generated_at=1_785_573_600,
        items=(
            ProfileItem(
                options=",id=200101",
                item_id=200101,
                item_name="Ring of Testing",
                fingerprint="b" * 64,
                best_slot="finger2",
                candidate_dps=126281.234,
                delta_percent=delta_percent,
                iterations=2500,
            ),
        ),
    )


def _harness_with_fallback() -> UIHarness:
    fallback_state = merge_profile(
        empty_state(), _record(name="Fallbackchar", spec_id=71, delta_percent=1.0)
    )
    return UIHarness(results_lua=render_aggregate_lua(fallback_state))


def _decode_and_apply(h: UIHarness, *, name: str, spec_id: int) -> None:
    h.execute("time = function() return 1785573700 end")
    text = encode_profile_transport(_record(name=name, spec_id=spec_id))
    ok, profile = h.eval(
        """
        function(text)
          local profile, err = LocalGearAdvisorNS.DecodeProfileTransport(text)
          if profile == nil then return false, err end
          return true, profile
        end
        """
    )(text)
    assert ok is True
    applied, err = h.eval("function(p) return LocalGearAdvisorNS.ApplyProfileTransport(p) end")(
        profile
    )
    assert applied is True, err


def _rows(h: UIHarness):
    table = h.eval("function() return LocalGearAdvisorNS.UI._profileRows end")()
    return list(table.values())


def _row_by_character(h: UIHarness, character_text: str):
    for row in _rows(h):
        if h.get_text(row["character"]) == character_text:
            return row
    raise AssertionError(f"no row found for {character_text!r}")


def test_empty_label_shown_when_no_profiles_and_hidden_once_one_exists() -> None:
    h = UIHarness(results_lua=render_aggregate_lua(empty_state()))
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    empty_label = h.eval("function() return LocalGearAdvisorNS.UI._emptyLabel end")()
    h.eval("function() LocalGearAdvisorNS.UI.RefreshProfiles() end")()
    assert h.is_shown(empty_label) is True

    _decode_and_apply(h, name="Testchar", spec_id=262)
    h.eval("function() LocalGearAdvisorNS.UI.RefreshProfiles() end")()

    assert h.is_shown(empty_label) is False


def test_profile_rows_render_fallback_and_imported_with_correct_source_labels() -> None:
    h = _harness_with_fallback()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()

    _decode_and_apply(h, name="Importedchar", spec_id=262)
    h.eval("function() LocalGearAdvisorNS.UI.RefreshProfiles() end")()

    rows = _rows(h)
    assert len(rows) == 2
    texts = {h.get_text(r["character"]): h.get_text(r["source"]) for r in rows}
    assert texts["Fallbackchar-examplerealm"] == "Results file"
    assert texts["Importedchar-examplerealm"] == "Imported"

    fallback_row = _row_by_character(h, "Fallbackchar-examplerealm")
    imported_row = _row_by_character(h, "Importedchar-examplerealm")
    assert h.is_shown(fallback_row["deleteButton"]) is False
    assert h.is_shown(imported_row["deleteButton"]) is True


def test_profile_row_actions_fit_inside_the_scroll_child_width() -> None:
    h = _harness_with_fallback()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    h.eval("function() LocalGearAdvisorNS.UI.RefreshProfiles() end")()
    row = _rows(h)[0]
    content_width, container_width = h.eval(
        """
        function(row)
          local width = 4 + row.character:GetWidth()
              + 6 + row.spec:GetWidth()
              + 6 + row.scenario:GetWidth()
              + 6 + row.items:GetWidth()
              + 6 + row.age:GetWidth()
              + 6 + row.source:GetWidth()
              + 8 + row.detailsButton:GetWidth()
              + 6 + row.deleteButton:GetWidth()
          return width, LocalGearAdvisorNS.UI._profilesContainer:GetWidth()
        end
        """
    )(row)

    assert content_width <= container_width


def test_profile_scroll_child_height_tracks_all_rendered_rows() -> None:
    state = empty_state()
    for index in range(30):
        state = merge_profile(state, _record(name=f"Char{index}", spec_id=1000 + index))
    h = UIHarness(results_lua=render_aggregate_lua(state))
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    h.eval("function() LocalGearAdvisorNS.UI.RefreshProfiles() end")()
    container = h.eval("function() return LocalGearAdvisorNS.UI._profilesContainer end")()

    assert h.method(container, "GetHeight") >= 30 * 20


def test_details_button_shows_panel_with_row_data_and_can_be_hidden() -> None:
    h = _harness_with_fallback()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    h.eval("function() LocalGearAdvisorNS.UI.RefreshProfiles() end")()

    details_panel = h.eval("function() return LocalGearAdvisorNS.UI._detailsPanel end")()
    assert h.is_shown(details_panel) is False

    row = _row_by_character(h, "Fallbackchar-examplerealm")
    h.click(row["detailsButton"])

    assert h.is_shown(details_panel) is True
    details_lines = h.eval("function() return LocalGearAdvisorNS.UI._detailsLines end")()
    assert h.get_text(details_lines["character"]) == "Fallbackchar-examplerealm"
    assert h.get_text(details_lines["source"]) == "Results file"

    h.eval("function() LocalGearAdvisorNS.UI.HideProfileDetails() end")()
    assert h.is_shown(details_panel) is False


def test_delete_requires_a_second_confirming_click_and_can_be_cancelled() -> None:
    h = _harness_with_fallback()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    _decode_and_apply(h, name="Importedchar", spec_id=262)
    h.eval("function() LocalGearAdvisorNS.UI.RefreshProfiles() end")()

    imported_row = _row_by_character(h, "Importedchar-examplerealm")
    assert h.get_text(imported_row["deleteLabel"]) == "Delete"

    h.click(imported_row["deleteButton"])  # 1st click: request confirmation only
    assert h.eval("function() return #(LocalGearAdvisorDB.profiles) end")() == 1
    imported_row_pending = _row_by_character(h, "Importedchar-examplerealm")
    assert h.get_text(imported_row_pending["deleteLabel"]) == "Really delete?"

    h.eval("function() LocalGearAdvisorNS.UI.CancelDeleteProfile() end")()
    imported_row_cancelled = _row_by_character(h, "Importedchar-examplerealm")
    assert h.get_text(imported_row_cancelled["deleteLabel"]) == "Delete"
    assert h.eval("function() return #(LocalGearAdvisorDB.profiles) end")() == 1

    h.click(imported_row_cancelled["deleteButton"])  # request again
    h.click(imported_row_cancelled["deleteButton"])  # confirm

    assert h.eval("function() return #(LocalGearAdvisorDB.profiles) end")() == 0
    visible_characters = {h.get_text(r["character"]) for r in _rows(h) if h.is_shown(r) is True}
    assert "Importedchar-examplerealm" not in visible_characters


def test_deleting_an_override_reports_that_the_results_file_fallback_is_revealed() -> None:
    fallback_state = merge_profile(empty_state(), _record(name="Testchar", spec_id=262))
    h = UIHarness(results_lua=render_aggregate_lua(fallback_state), now=1_785_573_700)
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    _decode_and_apply(h, name="Testchar", spec_id=262)
    h.eval("function() LocalGearAdvisorNS.UI.RefreshProfiles() end")()
    row = _row_by_character(h, "Testchar-examplerealm")

    h.click(row["deleteButton"])
    h.click(row["deleteButton"])

    status = h.eval("function() return LocalGearAdvisorNS.UI._undoStatus end")()
    assert "Results file" in h.get_text(status)
    revealed = _row_by_character(h, "Testchar-examplerealm")
    assert h.get_text(revealed["source"]) == "Results file"


def test_deleting_override_reports_visible_but_inactive_stale_fallback_in_both_locales() -> None:
    fallback_state = merge_profile(empty_state(), _record(name="Testchar", spec_id=262))
    for locale, expected in (
        ("enUS", "visible again, but it is stale and inactive"),
        ("deDE", "wieder sichtbar, aber veraltet und inaktiv"),
    ):
        h = UIHarness(
            results_lua=render_aggregate_lua(fallback_state),
            locale=locale,
            now=1_785_573_700,
        )
        h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
        _decode_and_apply(h, name="Testchar", spec_id=262)
        h.execute("time = function() return 2000000000 end")
        h.eval("function() LocalGearAdvisorNS.UI.RefreshProfiles() end")()
        row = _row_by_character(h, "Testchar-examplerealm")

        h.click(row["deleteButton"])
        h.click(row["deleteButton"])

        status = h.eval("function() return LocalGearAdvisorNS.UI._undoStatus end")()
        assert expected in h.get_text(status)


def test_deleting_the_currently_selected_profile_hides_its_details_panel() -> None:
    h = _harness_with_fallback()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    _decode_and_apply(h, name="Importedchar", spec_id=262)
    h.eval("function() LocalGearAdvisorNS.UI.RefreshProfiles() end")()

    imported_row = _row_by_character(h, "Importedchar-examplerealm")
    h.click(imported_row["detailsButton"])
    details_panel = h.eval("function() return LocalGearAdvisorNS.UI._detailsPanel end")()
    assert h.is_shown(details_panel) is True

    h.click(imported_row["deleteButton"])  # request
    h.click(imported_row["deleteButton"])  # confirm -> deletes selected profile

    assert h.is_shown(details_panel) is False


def test_delete_of_unknown_identity_leaves_the_db_untouched() -> None:
    h = _harness_with_fallback()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    _decode_and_apply(h, name="Importedchar", spec_id=262)

    ok, err = h.eval("function() return LocalGearAdvisorNS.DeleteDbProfile('nope') end")()

    assert ok is False
    assert h.eval("function() return #(LocalGearAdvisorDB.profiles) end")() == 1


def test_undo_restores_a_deleted_profile_and_refreshes_the_list() -> None:
    h = _harness_with_fallback()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    _decode_and_apply(h, name="Importedchar", spec_id=262)
    h.eval("function() LocalGearAdvisorNS.UI.RefreshProfiles() end")()

    imported_row = _row_by_character(h, "Importedchar-examplerealm")
    h.click(imported_row["deleteButton"])  # request
    h.click(imported_row["deleteButton"])  # confirm
    assert h.eval("function() return #(LocalGearAdvisorDB.profiles) end")() == 0

    undo_button = h.eval("function() return LocalGearAdvisorNS.UI._undoButton end")()
    h.click(undo_button)

    assert h.eval("function() return #(LocalGearAdvisorDB.profiles) end")() == 1
    undo_status = h.eval("function() return LocalGearAdvisorNS.UI._undoStatus end")()
    assert h.get_text(undo_status) == "Last change undone."
    rows_final = _rows(h)
    assert any(h.get_text(r["character"]) == "Importedchar-examplerealm" for r in rows_final)


def test_undo_button_shows_error_message_when_nothing_to_undo() -> None:
    h = _harness_with_fallback()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()

    undo_button = h.eval("function() return LocalGearAdvisorNS.UI._undoButton end")()
    h.click(undo_button)

    undo_status = h.eval("function() return LocalGearAdvisorNS.UI._undoStatus end")()
    assert h.get_text(undo_status).startswith("Undo unavailable: ")
