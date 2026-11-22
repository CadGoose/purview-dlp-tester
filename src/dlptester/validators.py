"""Checksum / format validators applied to a primary-element match."""

from __future__ import annotations

from collections.abc import Callable


def digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def luhn(value: str) -> bool:
    """Mod-10 Luhn check, used by SIN, OHIP and payment cards."""
    d = digits(value)
    if not d:
        return False
    total = 0
    for i, ch in enumerate(reversed(d)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def card_issuer(value: str) -> bool:
    """Known PAN prefixes and lengths (Visa, Mastercard, Amex, Discover)."""
    d = digits(value)
    n = len(d)
    if d.startswith("4") and n in (13, 16, 19):
        return True
    if n == 16 and (51 <= int(d[:2]) <= 55 or 2221 <= int(d[:4]) <= 2720):
        return True
    if n == 15 and d[:2] in ("34", "37"):
        return True
    if n == 16 and (d.startswith("6011") or d.startswith("65")):
        return True
    return False


def not_repeating(value: str) -> bool:
    """Reject 000000000 / 111111111-style placeholders."""
    d = digits(value)
    return len(set(d)) > 1


VALIDATORS: dict[str, Callable[[str], bool]] = {
    "luhn": luhn,
    "card_issuer": card_issuer,
    "not_repeating": not_repeating,
}
