from __future__ import annotations

from datetime import time

import pytest

from timetracker.services.settings_service import (
    KEY_MANDATORY_CLIENT,
    KEY_WORKDAY_START,
    SettingsService,
)


def test_defaults(settings_service: SettingsService) -> None:
    assert settings_service.mandatory_client is True
    assert settings_service.mandatory_type is True
    assert settings_service.workday_start == time(9, 0)
    assert settings_service.get("no.such.key") is None


def test_set_persists_and_signals_once(settings_service: SettingsService, qtbot) -> None:  # type: ignore[no-untyped-def]
    with qtbot.waitSignal(settings_service.setting_changed, timeout=1000) as blocker:
        settings_service.set(KEY_MANDATORY_CLIENT, False)
    assert blocker.args == [KEY_MANDATORY_CLIENT]
    assert settings_service.mandatory_client is False
    with qtbot.assertNotEmitted(settings_service.setting_changed):
        settings_service.set(KEY_MANDATORY_CLIENT, False)  # unchanged → no signal


def test_workday_start_falls_back_on_garbage(settings_service: SettingsService) -> None:
    settings_service.set(KEY_WORKDAY_START, "08:30")
    assert settings_service.workday_start == time(8, 30)
    settings_service.set(KEY_WORKDAY_START, "noon")
    assert settings_service.workday_start == time(9, 0)


def test_export_presets_round_trip_through_settings(settings_service: SettingsService) -> None:
    """FR-608: presets live in the setting table as one JSON list."""
    from timetracker.core.errors import ValidationError
    from timetracker.core.export_presets import ExportPreset
    from timetracker.services.settings_service import KEY_EXPORT_PRESETS

    assert settings_service.export_presets().presets == ()
    preset = ExportPreset("Monthly", "csv", ("Date", "Client", "Duration (decimal hours)"), 6)
    settings_service.save_export_preset(preset)
    assert settings_service.export_presets().get("monthly") == preset
    assert isinstance(settings_service.get(KEY_EXPORT_PRESETS), list)
    with pytest.raises(ValidationError):
        settings_service.save_export_preset(ExportPreset("", "csv", ("Date",)))
    settings_service.remove_export_preset("Monthly")
    assert settings_service.export_presets().presets == ()
