"""Public Basic identity, including replay of receipts from the local 0.10 build."""

from enum import Enum


class HudVariant(str, Enum):
    """Only the existing menu is allowed in the public edition."""

    BASIC = 'basic'

    @property
    def payload_filename(self) -> str:
        return 'classes23.dex'

    @property
    def metadata_filename(self) -> str:
        return 'payload.json'


def validate_variant(value: object) -> HudVariant:
    """Accept exact variant names, never paths, aliases or implicit defaults."""
    if isinstance(value, str):
        try:
            return HudVariant(value)
        except ValueError:
            pass
    raise ValueError('Public menu variant must be basic.')
