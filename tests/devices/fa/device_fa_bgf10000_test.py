"""BGF10000 mode/speed presets captured from the Midea App."""

from unittest.mock import patch

import pytest

from midealan.const import ProtocolVersion
from midealan.devices.fa import DeviceAttributes, MideaFADevice

PRESETS = [
    ("normal", 1, None),
    ("forest", 4, 1),
    ("beach", 4, 2),
    ("countryside", 4, 3),
    ("baby", 3, 1),
    ("sleep_1", 3, 2),
    ("sleep_2", 3, 3),
    ("strong", 9, 12),
]


def _make_device(
    model: str = "BGF10000",
    subtype: int = 15,
    customize: str = "",
) -> MideaFADevice:
    """Create an offline device."""
    return MideaFADevice(
        name="Test fan",
        device_id=1,
        ip_address="192.0.2.1",
        port=6444,
        token="",
        key="",
        device_protocol=ProtocolVersion.V3,
        model=model,
        subtype=subtype,
        customize=customize,
    )


@pytest.mark.parametrize(
    ("preset", "mode_speed", "checksum"),
    [
        ("forest", "0901", "98"),
        ("beach", "0902", "97"),
        ("countryside", "0903", "96"),
        ("baby", "0701", "9a"),
        ("sleep_1", "0702", "99"),
        ("sleep_2", "0703", "98"),
        ("strong", "130c", "83"),
        ("normal", "030c", "93"),
    ],
)
def test_captured_responses(preset: str, mode_speed: str, checksum: str) -> None:
    """Decode App presets without exposing submode numbers as motor speed."""
    device = _make_device()
    status = device.process_message(
        bytes.fromhex(
            "aa1efa0000000000000300000000"
            f"{mode_speed}00004300000000000000ffff0200{checksum}",
        ),
    )
    assert status[DeviceAttributes.mode] == preset
    assert device.get_attribute(DeviceAttributes.mode) == preset
    speed = 12 if preset in {"normal", "strong"} else None
    assert status[DeviceAttributes.fan_speed] == speed
    assert device.get_attribute(DeviceAttributes.fan_speed) == speed


@pytest.mark.parametrize(("preset", "mode", "speed"), PRESETS)
@pytest.mark.parametrize("use_turn_on", [False, True])
def test_combined_preset_command(
    preset: str,
    mode: int,
    speed: int | None,
    use_turn_on: bool,
) -> None:
    """Send the preset atomically through either public control API."""
    device = _make_device()
    with patch.object(device, "build_send") as send:
        if use_turn_on:
            device.turn_on(fan_speed=6, mode=preset)
        else:
            device.set_attribute(DeviceAttributes.mode, preset)
    send.assert_called_once()
    message = send.call_args.args[0]
    assert message.mode == mode
    expected_speed = 6 if use_turn_on and speed is None else speed
    assert message.fan_speed == expected_speed
    assert message.power is True
    assert message.body[4:6] == bytes((1 | (mode << 1), expected_speed or 0))


@pytest.mark.parametrize("power", [False, True])
def test_speed_leaves_submode(power: bool) -> None:
    """An explicit speed selects normal wind even while already powered on."""
    device = _make_device()
    device.attributes[DeviceAttributes.power] = power
    with patch.object(device, "build_send") as send:
        device.set_attribute(DeviceAttributes.fan_speed, 6)
    message = send.call_args.args[0]
    assert (message.mode, message.fan_speed, message.power) == (1, 6, True)


def test_plain_power_and_zero_speed() -> None:
    """Preserve submodes on power commands and the existing zero-speed API."""
    device = _make_device()
    with patch.object(device, "build_send") as send:
        device.turn_on()
    message = send.call_args.args[0]
    assert (message.mode, message.fan_speed, message.power) == (None, None, True)
    with patch.object(device, "build_send") as send:
        device.set_attribute(DeviceAttributes.power, False)
    assert send.call_args.args[0].power is False
    with patch.object(device, "build_send") as send:
        device.set_attribute(DeviceAttributes.fan_speed, 0)
    send.assert_not_called()


@pytest.mark.parametrize("mode", ["comfort", "sleep", "natural", "missing"])
def test_unsupported_presets(mode: str) -> None:
    """Ignore unsupported broad/legacy modes instead of sending wrong commands."""
    device = _make_device()
    with patch.object(device, "build_send") as send:
        device.set_attribute(DeviceAttributes.mode, mode)
        device.turn_on(mode=mode)
    send.assert_not_called()


def test_unknown_submode_and_power_off() -> None:
    """Unknown submodes remain unknown and off state keeps speed zero."""
    device = _make_device()
    unknown = device.process_message(
        bytes.fromhex(
            "aa1efa0000000000000300000000090400004300000000000000ffff020095",
        ),
    )
    assert unknown[DeviceAttributes.mode] is None
    assert unknown[DeviceAttributes.fan_speed] is None
    off = device.process_message(
        bytes.fromhex(
            "aa1efa0000000000000300000000060100004300000000000000ffff02009b",
        ),
    )
    assert off[DeviceAttributes.power] is False
    assert off[DeviceAttributes.fan_speed] == 0
    assert off[DeviceAttributes.mode] == "baby"


def test_speed_count_and_preset_options() -> None:
    """Default to the confirmed 12-speed range and retain explicit overrides."""
    device = _make_device()
    assert device.speed_count == 12
    assert device.preset_modes == [item[0] for item in PRESETS]
    device.set_customize('{"speed_count": 6}')
    assert device.speed_count == 6
    device.set_customize("")
    assert device.speed_count == 12


@pytest.mark.parametrize(
    ("model", "subtype"),
    [("BGF10000", 14), ("56000211", 15), ("other", 15)],
)
def test_other_models_and_subtypes_unchanged(model: str, subtype: int) -> None:
    """Keep the generic FA presets, speed count, and wire behavior."""
    device = _make_device(model, subtype)
    assert device.speed_count == 3
    assert "comfort" in device.preset_modes
    assert "forest" not in device.preset_modes
    with patch.object(device, "build_send") as send:
        device.set_attribute(DeviceAttributes.mode, "comfort")
    message = send.call_args.args[0]
    assert (message.mode, message.fan_speed) == (4, None)
    device.attributes[DeviceAttributes.power] = True
    with patch.object(device, "build_send") as send:
        device.set_attribute(DeviceAttributes.fan_speed, 6)
    assert send.call_args.args[0].mode is None
