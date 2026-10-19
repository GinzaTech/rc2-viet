"""Closed HUD variant identifiers and their fixed bundled asset names."""

from enum import Enum


class HudVariant(str, Enum):
    """The two independently built menu payloads."""

    BASIC = 'basic'
    ADVANCED = 'advanced'

    @property
    def payload_filename(self) -> str:
        return 'classes23.dex' if self is HudVariant.BASIC else 'advanced.dex'

    @property
    def metadata_filename(self) -> str:
        return 'payload.json' if self is HudVariant.BASIC else 'advanced-payload.json'


def validate_variant(value: object) -> HudVariant:
    """Accept exact variant names, never paths, aliases or implicit defaults."""
    if isinstance(value, str):
        try:
            return HudVariant(value)
        except ValueError:
            pass
    raise ValueError('HUD variant must be basic or advanced.')
