import pytest

from app.workers.paper_style_polarization import (
    CAT_FREEDOM,
    CAT_POPULISM,
    CAT_STATE,
    sentiment_intensity,
    sentiment_polarity_score,
    stance_label_and_strength,
    transmissibility,
)


def test_sentiment_polarity_score_in_zero_one_range():
    score = sentiment_polarity_score("支持,合理,有必要")
    assert 0.0 <= score <= 1.0
    assert score > 0.5


def test_sentiment_intensity_formula():
    assert sentiment_intensity(0.9, 0.5) == 0.4
    assert sentiment_intensity(0.2, 0.5) == 0.3


def test_transmissibility_formula():
    assert transmissibility(0.8, 0.7) == pytest.approx(0.9, abs=1e-9)
    assert transmissibility(0.2, 0.8) == pytest.approx(0.4, abs=1e-9)


def test_stance_label_and_strength():
    label, strength, gap, entropy_pol = stance_label_and_strength(0.8, 0.2, 0.1)
    assert label == CAT_STATE
    assert strength > 0.0
    assert gap > 0.0
    assert 0.0 <= entropy_pol <= 1.0

    label2, _, _, _ = stance_label_and_strength(0.01, 0.01, 0.01)
    assert label2 == "neutral"

    label3, *_ = stance_label_and_strength(0.1, 0.7, 0.2)
    assert label3 == CAT_FREEDOM

    label4, *_ = stance_label_and_strength(0.1, 0.2, 0.7)
    assert label4 == CAT_POPULISM
