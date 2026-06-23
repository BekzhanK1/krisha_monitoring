from __future__ import annotations

from app.models.seller import SellerType

_BASE_OWNER = 0.85
_BASE_AGENT = 0.25
_BASE_AGENCY = 0.10
_BASE_UNKNOWN = 0.50

_OWNER_KEYWORDS = ("собственник", "хозяин", "от собственника")
_AGENT_KEYWORDS = ("риелтор", "агентство", "риэлтор")

_OWNER_KEYWORD_BONUS = 0.10
_AGENT_KEYWORD_PENALTY = 0.15


def estimate_owner_probability(
    *,
    seller_type: SellerType | None,
    description: str | None,
    seller_name: str | None = None,
) -> float:
    """Return 0.0–1.0 probability seller is owner."""
    score = _base_for_seller_type(seller_type)
    text = _combined_text(description, seller_name)

    if text and _contains_any(text, _OWNER_KEYWORDS):
        score += _OWNER_KEYWORD_BONUS
    if text and _contains_any(text, _AGENT_KEYWORDS):
        score -= _AGENT_KEYWORD_PENALTY

    return _clamp(score)


def _base_for_seller_type(seller_type: SellerType | None) -> float:
    if seller_type is None:
        return _BASE_UNKNOWN
    if seller_type is SellerType.OWNER:
        return _BASE_OWNER
    if seller_type is SellerType.AGENT:
        return _BASE_AGENT
    if seller_type is SellerType.AGENCY:
        return _BASE_AGENCY
    return _BASE_UNKNOWN


def _combined_text(description: str | None, seller_name: str | None) -> str:
    parts = [part for part in (description, seller_name) if part]
    return " ".join(parts).lower()


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
