from __future__ import annotations

import pytest

from app.analyzer.seller_scorer import estimate_owner_probability
from app.models.seller import SellerType


@pytest.mark.parametrize(
    ("seller_type", "expected"),
    [
        (SellerType.OWNER, 0.85),
        (SellerType.AGENT, 0.25),
        (SellerType.AGENCY, 0.10),
        (None, 0.50),
    ],
)
def test_base_probability_by_seller_type(
    seller_type: SellerType | None,
    expected: float,
) -> None:
    assert estimate_owner_probability(
        seller_type=seller_type,
        description=None,
    ) == pytest.approx(expected)


def test_owner_keyword_in_description_boosts_score() -> None:
    score = estimate_owner_probability(
        seller_type=SellerType.AGENT,
        description="Квартира от собственника, без посредников",
    )
    assert score == pytest.approx(0.35)


def test_agent_keyword_in_description_lowers_score() -> None:
    score = estimate_owner_probability(
        seller_type=SellerType.OWNER,
        description="Предлагает агентство недвижимости",
    )
    assert score == pytest.approx(0.70)


def test_keywords_in_seller_name_are_considered() -> None:
    score = estimate_owner_probability(
        seller_type=None,
        description=None,
        seller_name="Риелтор Айгуль",
    )
    assert score == pytest.approx(0.35)


def test_clamp_lower_bound() -> None:
    score = estimate_owner_probability(
        seller_type=SellerType.AGENCY,
        description="агентство риелтор риэлтор",
    )
    assert score == 0.0


def test_clamp_upper_bound() -> None:
    score = estimate_owner_probability(
        seller_type=SellerType.OWNER,
        description="собственник хозяин от собственника",
    )
    assert score == pytest.approx(0.95)
    assert score <= 1.0
