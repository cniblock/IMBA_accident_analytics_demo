"""Shared UI copy and methodology disclaimers."""

HARM_INDEX_CAPTION = (
    "Harm Index is an internal ranking heuristic (fatal × 5 + serious × 2 + slight × 1). "
    "It is not an official STATS19 metric and should not be used as a standalone legal or policy measure."
)

TRIAGE_HARM_CAPTION = (
    "Triage and harm scores are rule-based heuristics combining context factors (light, speed, weather, "
    "vehicle type, driver age) and collision severity. They support triage prioritisation only — "
    "not predictive modelling or liability assessment."
)

PRIORITY_QUEUE_CAPTION = (
    "Priority scores rank casualties for review using reported severity, vulnerable age bands, "
    "distance from home, and pedestrian-at-night context. Scores are transparent heuristics, not ML predictions."
)

PROVISIONAL_DATA_NOTICE = (
    "This dataset includes **provisional 2025 STATS19 records**. Figures for 2025 may change when "
    "DfT publishes final validated data."
)
