"""Model-specific FA preset profiles."""

from dataclasses import dataclass
from typing import Protocol


class PresetMessage(Protocol):
    """Message fields used by an FA preset profile."""

    power: bool | None
    mode: int | None
    fan_speed: int | None


@dataclass(frozen=True)
class FAPresetProfile:
    """Map model-specific public presets to the generic FA mode/gear fields."""

    model: str
    subtype: int
    speed_count: int
    presets: dict[str, tuple[int, int | None]]
    submode_codes: frozenset[int]

    def matches(self, model: str, subtype: int) -> bool:
        """Return whether this profile applies to a device."""
        return model == self.model and subtype == self.subtype

    def decode(
        self,
        raw_mode: int,
        raw_speed: int | None,
        power: bool,
    ) -> tuple[str | None, int | None]:
        """Decode an overloaded mode/gear pair into public mode and speed."""
        preset = next(
            (
                name
                for name, (mode, speed) in self.presets.items()
                if mode == raw_mode and (speed is None or speed == raw_speed)
            ),
            None,
        )
        if not power:
            return preset, 0
        if raw_mode in self.submode_codes:
            # These gear values identify App submodes, not motor speeds.
            return preset, None
        return preset, raw_speed

    def apply(
        self,
        message: PresetMessage,
        fan_speed: int | None,
        preset: str | None,
    ) -> bool:
        """Apply a model-specific preset or explicit speed to one command."""
        if preset is not None and preset not in self.presets:
            return False
        message.power = True
        if fan_speed is not None:
            message.fan_speed = fan_speed
        if preset is not None:
            message.mode, preset_speed = self.presets[preset]
            if preset_speed is not None:
                message.fan_speed = preset_speed
        elif fan_speed is not None:
            # Explicit motor-speed selection leaves an overloaded submode.
            message.mode = self.presets["normal"][0]
        return True


# T_0000_FA_17.lua defines mode and gear as independent generic FA fields. The
# names below are App semantics confirmed only by BGF10000 subtype 15 captures;
# do not broaden the profile without equivalent evidence from another device.
BGF10000_PROFILE = FAPresetProfile(
    model="BGF10000",
    subtype=15,
    speed_count=12,
    presets={
        "normal": (0x01, None),
        "forest": (0x04, 1),
        "beach": (0x04, 2),
        "countryside": (0x04, 3),
        "baby": (0x03, 1),
        "sleep_1": (0x03, 2),
        "sleep_2": (0x03, 3),
        "strong": (0x09, 12),
    },
    submode_codes=frozenset({0x03, 0x04}),
)

FA_PRESET_PROFILES = (BGF10000_PROFILE,)


def get_preset_profile(model: str, subtype: int) -> FAPresetProfile | None:
    """Return the verified model/subtype preset profile, if any."""
    return next(
        (profile for profile in FA_PRESET_PROFILES if profile.matches(model, subtype)),
        None,
    )
