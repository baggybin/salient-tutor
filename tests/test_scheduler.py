"""Scheduler arithmetic tests — SM-2 / FSRS-lite spaced repetition.

Pins the exact numbers from the kernel's tutor/schedule.py so a scheduler
regression is caught immediately. These numbers are load-bearing — they
define the learner's mastery curve.
"""

import pytest
from salient_core.tutor.schedule import (
    _INITIAL_DAYS,
    _INITIAL_MASTERY,
    _LAPSE_FLOOR_DAYS,
    _MAX_DAYS,
    _MIN_DAYS,
    GRADES,
    STRONG_THRESHOLD,
    next_interval_days,
    next_mastery,
    normalize_grade,
    predicate_for,
)


class TestGradeVocabulary:
    def test_four_grades(self):
        assert GRADES == ("again", "hard", "good", "easy")

    @pytest.mark.parametrize("grade", ["again", "hard", "good", "easy"])
    def test_normalize_accepts_valid(self, grade):
        assert normalize_grade(grade) == grade
        assert normalize_grade(grade.upper()) == grade
        assert normalize_grade(f"  {grade}  ") == grade

    def test_normalize_rejects_invalid(self):
        with pytest.raises(ValueError):
            normalize_grade("medium")
        with pytest.raises(ValueError):
            normalize_grade("")


class TestIntervalScheduler:
    """next_interval_days — first-review table + growth multipliers + clamp."""

    def test_first_review_again(self):
        assert next_interval_days(None, "again") == _LAPSE_FLOOR_DAYS

    def test_first_review_good(self):
        assert next_interval_days(None, "good") == _INITIAL_DAYS["good"]

    def test_first_review_easy(self):
        assert next_interval_days(None, "easy") == _INITIAL_DAYS["easy"]

    def test_success_growth(self):
        prev = next_interval_days(None, "good")
        nxt = next_interval_days(prev, "good")
        assert nxt > prev

    def test_lapse_resets_to_floor(self):
        prev = 30.0
        reset = next_interval_days(prev, "again")
        assert reset == _LAPSE_FLOOR_DAYS

    def test_clamp_min(self):
        assert next_interval_days(0.5, "hard") >= _MIN_DAYS

    def test_clamp_max(self):
        big = next_interval_days(_MAX_DAYS - 1, "easy")
        assert big <= _MAX_DAYS


class TestMasteryScheduler:
    """next_mastery — asymptotic toward 1.0, lapse toward 0.0."""

    def test_cold_start(self):
        """First review applies a gain on top of initial mastery (0.3)."""
        m = next_mastery(None, "good")
        assert m > _INITIAL_MASTERY  # 0.51 > 0.3
        assert m < 1.0

    def test_success_raises(self):
        m1 = next_mastery(None, "good")
        m2 = next_mastery(m1, "good")
        assert m2 > m1

    def test_lapse_lowers(self):
        m1 = next_mastery(None, "good")
        m2 = next_mastery(m1, "again")
        assert m2 < m1

    def test_asymptotic(self):
        """Mastery approaches but never reaches 1.0."""
        m = 0.99
        m_next = next_mastery(m, "easy")
        assert m_next > m
        assert m_next < 1.0

    def test_clamped_01(self):
        m = 0.01
        m_next = next_mastery(m, "again")
        assert m_next >= 0.0


class TestPredicateFor:
    """predicate_for — the strong/weak threshold line."""

    def test_strong_at_threshold(self):
        assert predicate_for(STRONG_THRESHOLD) == "strong_topic"

    def test_strong_above(self):
        assert predicate_for(0.9) == "strong_topic"

    def test_weak_below(self):
        assert predicate_for(0.1) == "weak_topic"

    def test_weak_just_below(self):
        assert predicate_for(STRONG_THRESHOLD - 0.01) == "weak_topic"
