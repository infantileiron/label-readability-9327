"""Regression tests for the exact test and direction interval used by the p-value bounds."""
from src.services.statistics import direction_interval, exact_mcnemar


def test_documented_mcnemar_value():
    assert exact_mcnemar(2, 12) == 0.012939453125


def test_documented_direction_interval():
    lower, upper = direction_interval(12, 14, 95)
    assert round(lower * 100, 1) == 57.2
    assert round(upper * 100, 1) == 98.2


def test_zero_discordant_is_one():
    assert exact_mcnemar(0, 0) == 1.0
    assert direction_interval(0, 0, 95) is None
