from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PokerKitValidation:
    available: bool
    accepted: bool
    reference: str | None
    error: str | None


def validate_standard_high(cards: tuple[str, ...] | list[str]) -> PokerKitValidation:
    """Valide une main avec PokerKit sans exposer ses objets au reste du projet."""

    try:
        from pokerkit import StandardHighHand
    except ImportError:
        return PokerKitValidation(False, False, None, "PokerKit indisponible")
    try:
        hand: Any = StandardHighHand.from_game("".join(cards))
    except (TypeError, ValueError, AttributeError) as exc:
        return PokerKitValidation(True, False, None, f"API PokerKit incompatible: {exc}")
    return PokerKitValidation(True, True, str(hand), None)
