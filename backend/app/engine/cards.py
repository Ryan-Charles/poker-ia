from __future__ import annotations

from dataclasses import dataclass

RANKS = "23456789TJQKA"
SUITS = "shdc"
RANK_VALUE = {rank: value for value, rank in enumerate(RANKS, start=2)}
SUIT_NAMES = {"s": "pique", "h": "cœur", "d": "carreau", "c": "trèfle"}
RANK_NAMES = {
    "A": "As",
    "K": "Roi",
    "Q": "Dame",
    "J": "Valet",
    "T": "10",
    **{str(value): str(value) for value in range(2, 10)},
}


class CardError(ValueError):
    """Carte invalide ou dupliquée."""


@dataclass(frozen=True, slots=True, order=True)
class Card:
    rank: str
    suit: str

    def __post_init__(self) -> None:
        if self.rank not in RANKS or self.suit not in SUITS:
            raise CardError(f"Carte invalide: {self.rank}{self.suit}")

    @property
    def value(self) -> int:
        return RANK_VALUE[self.rank]

    @property
    def code(self) -> str:
        return f"{self.rank}{self.suit}"

    @property
    def french_name(self) -> str:
        return f"{RANK_NAMES[self.rank]} de {SUIT_NAMES[self.suit]}"


def normalize_card(value: str) -> str:
    cleaned = value.strip().replace("♠", "s").replace("♥", "h").replace("♦", "d").replace("♣", "c")
    if len(cleaned) == 3 and cleaned[:2] == "10":
        cleaned = "T" + cleaned[2]
    if len(cleaned) != 2:
        raise CardError(f"Code de carte invalide: {value!r}")
    rank = cleaned[0].upper()
    suit = cleaned[1].lower()
    return Card(rank, suit).code


def parse_card(value: str) -> Card:
    normalized = normalize_card(value)
    return Card(normalized[0], normalized[1])


def full_deck() -> tuple[str, ...]:
    return tuple(f"{rank}{suit}" for suit in SUITS for rank in RANKS)


def ensure_unique(cards: list[str] | tuple[str, ...]) -> list[str]:
    normalized = [normalize_card(card) for card in cards]
    if len(normalized) != len(set(normalized)):
        raise CardError("Une même carte ne peut pas être utilisée plusieurs fois")
    return normalized


def canonical_hole_class(cards: list[str] | tuple[str, str]) -> str:
    if len(cards) != 2:
        raise CardError("Deux cartes sont nécessaires")
    first, second = (parse_card(card) for card in cards)
    ordered = sorted((first, second), key=lambda card: card.value, reverse=True)
    if ordered[0].rank == ordered[1].rank:
        return ordered[0].rank * 2
    suffix = "s" if ordered[0].suit == ordered[1].suit else "o"
    return f"{ordered[0].rank}{ordered[1].rank}{suffix}"
