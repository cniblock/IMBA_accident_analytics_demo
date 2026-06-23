"""Unit tests for transforms module."""

import unittest

import numpy as np
import pandas as pd

from transforms import (
    apply_code_labels,
    casualty_priority_reason,
    casualty_priority_score,
    collision_level_serious_fatal_stats,
    has_required_columns,
    harm_score_features,
    safe_ratio,
    triage_score_features,
    validate_schema,
)


class TestSchemaValidation(unittest.TestCase):
    def test_validate_schema_reports_missing(self):
        df = pd.DataFrame({"a": [1]})
        self.assertEqual(validate_schema(df, ["a", "b"]), ["b"])

    def test_has_required_columns(self):
        df = pd.DataFrame({"collision_index": ["1"]})
        self.assertTrue(has_required_columns(df, ["collision_index"]))
        self.assertFalse(has_required_columns(df, ["date"]))


class TestSafeRatio(unittest.TestCase):
    def test_zero_denominator_returns_zero(self):
        result = safe_ratio(pd.Series([1, 2]), pd.Series([0, 2]))
        pd.testing.assert_series_equal(result, pd.Series([0.0, 1.0]))


class TestCodeLabels(unittest.TestCase):
    def test_apply_code_labels(self):
        df = pd.DataFrame({"collision_severity": [1, 2, 3]})
        maps = {"collision_severity": {1: "Fatal", 2: "Serious", 3: "Slight"}}
        out = apply_code_labels(df, maps)
        self.assertListEqual(
            out["collision_severity_label"].tolist(),
            ["Fatal", "Serious", "Slight"],
        )


class TestScoring(unittest.TestCase):
    def _vehicle_row(self, **kwargs):
        base = {
            "is_dark": 0,
            "speed_limit": 30,
            "urban_or_rural_area": 1,
            "weather_conditions": 1,
            "road_surface_conditions": 1,
            "vehicle_type": 9,
            "age_of_driver": 40,
            "collision_severity": 3,
            "skidding_and_overturning": 0,
            "vehicle_leaving_carriageway": 0,
            "hit_object_off_carriageway": 0,
        }
        base.update(kwargs)
        return pd.DataFrame([base])

    def test_triage_score_increases_with_risk_factors(self):
        low = triage_score_features(self._vehicle_row()).iloc[0]
        high = triage_score_features(
            self._vehicle_row(is_dark=1, speed_limit=60, urban_or_rural_area=2)
        ).iloc[0]
        self.assertGreater(high, low)

    def test_harm_score_includes_fatal_severity(self):
        slight = harm_score_features(self._vehicle_row(collision_severity=3)).iloc[0]
        fatal = harm_score_features(self._vehicle_row(collision_severity=1)).iloc[0]
        self.assertGreater(fatal, slight)

    def test_casualty_priority_fatal_outranks_slight(self):
        df = pd.DataFrame(
            [
                {
                    "casualty_severity": 1,
                    "age_of_casualty": 40,
                    "casualty_distance_banding": 1,
                    "speed_limit": 30,
                    "is_dark": 0,
                    "casualty_class": 9,
                },
                {
                    "casualty_severity": 3,
                    "age_of_casualty": 40,
                    "casualty_distance_banding": 1,
                    "speed_limit": 30,
                    "is_dark": 0,
                    "casualty_class": 9,
                },
            ]
        )
        scores = casualty_priority_score(df)
        self.assertGreater(scores.iloc[0], scores.iloc[1])
        self.assertEqual(casualty_priority_reason(df).iloc[0], "Fatal casualty")


class TestCollisionLevelStats(unittest.TestCase):
    def test_deduplicates_collisions_for_rate(self):
        df = pd.DataFrame(
            {
                "vehicle_type_label": ["Car", "Car", "Car"],
                "collision_index": ["A", "A", "B"],
                "fatal_collision": [1, 1, 0],
                "serious_collision": [0, 0, 1],
                "serious_or_fatal_collision": [1, 1, 1],
            }
        )
        stats = collision_level_serious_fatal_stats(df, ["vehicle_type_label"])
        self.assertEqual(int(stats.iloc[0]["collisions"]), 2)
        self.assertEqual(int(stats.iloc[0]["serious_or_fatal_collisions"]), 2)
        self.assertAlmostEqual(float(stats.iloc[0]["serious_fatal_collision_rate_pct"]), 100.0)


if __name__ == "__main__":
    unittest.main()
