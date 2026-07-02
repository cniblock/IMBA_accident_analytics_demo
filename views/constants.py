"""Shared UI copy and methodology disclaimers."""

HARM_INDEX_CAPTION = (
    "**Harm Index** = fatal casualties × 5 + serious casualties × 2 + slight casualties × 1. "
    "Internal ranking heuristic only — not an official STATS19 metric."
)

HARM_INDEX_SHORT = "fatal × 5 + serious × 2 + slight × 1"

UNADJUSTED_COUNTS_CAPTION = (
    "District counts are **not adjusted** for population, road length, or traffic volume. "
    "Large urban authorities often rank higher on raw counts alone."
)

METRIC_UNITS_CAPTION = (
    "**Collision records** count STATS19 collision events. **Casualty** metrics count people injured "
    "(one collision may involve multiple casualties)."
)

NIGHT_TIME_DEFINITION = (
    "Share of collision **records** where light condition is darkness or dark lighting "
    "(STATS19 codes 4–7: lights lit/unlit, no lighting, darkness with/without lighting)."
)

TRIAGE_HARM_CAPTION = (
    "Triage and harm scores are rule-based heuristics combining context factors (light, speed, weather, "
    "vehicle type, driver age) and collision severity. They support triage prioritisation only — "
    "not predictive modelling or liability assessment."
)

PRIORITY_QUEUE_CAPTION = (
    "Priority cases are selected for **analytical review** using transparent rules. "
    "Scores are heuristics, not ML predictions. They do **not** imply liability, causation, or preventability."
)

CASUALTY_RECORD_CONTEXT = (
    "This page is analysed at **casualty-record level**. A single collision may include multiple casualties, "
    "so casualty totals differ from collision totals."
)

KSI_SHARE_LABEL = "KSI share (%)"

KSI_SHARE_DEFINITION = (
    "**KSI share** = fatal + serious casualties as a percentage of **recorded casualties** in the current filter. "
    "This is not a population rate, exposure rate, or per-trip risk measure."
)

DEPRIVATION_CAVEAT = (
    "Deprivation decile is based on the **linked casualty IMD field** (casualty home-area deprivation). "
    "It should not be interpreted as collision-location deprivation, complete exposure, travel behaviour, "
    "or area-level road danger."
)

DISTRICT_CASUALTY_CAVEAT = (
    "District tables use **raw casualty counts and harm scores** — not adjusted for population, "
    "pedestrian exposure, road length, or traffic volume."
)

CROSSING_FACILITY_CAVEAT = (
    "Crossing-facility KSI shares are **not exposure-adjusted**. High rates may reflect where facilities "
    "are installed (complex, high-speed, high-volume roads) — not that crossings cause harm."
)

HOURLY_KSI_CAVEAT = (
    "Hourly KSI shares should be read alongside **casualty volume** — overnight hours often have smaller denominators."
)

REPORTING_MODE_DEFINITION = (
    "**Reporting mode** describes how the collision/casualty was reported in STATS19 (e.g. police attendance vs "
    "self-completion). Differences in KSI share may reflect reporting channel, severity, and data-capture effects."
)

LINKAGE_PEDESTRIAN_NOTE = (
    "**Pedestrian casualties** are not vehicle records, so they show zero in vehicle-linkage counts. "
    "Counterpart-vehicle analysis would require linking casualties to involved vehicles in the same collision."
)

MISSING_AGE_NOTE = (
    "**Missing** age is excluded from age-pattern charts and shown separately for data-quality context."
)

HEATMAP_MIN_N_NOTE = "Cells/groups with fewer than 30 casualties are excluded from ranked heatmaps and rate charts."

PROVISIONAL_DATA_NOTICE = (
    "This dataset includes **provisional 2025 STATS19 records**. Figures for 2025 may change when "
    "DfT publishes final validated data."
)

EXPOSURE_CAVEAT = (
    "Counts are **not exposure-adjusted**. High values may reflect common driving conditions "
    "rather than higher per-journey risk — use **KSI rate** charts alongside volume."
)

SPECIFIED_ROAD_CAVEAT = (
    "Specified-road rankings use **raw STATS19 counts** and are not normalised by road length or traffic volume."
)

TRUNK_ROAD_NOTE = (
    "**Trunk roads** are strategic roads managed by **National Highways**. Non-trunk roads are generally "
    "local authority roads. **Data missing or out of range** is a data-quality category — not a governance group."
)

SPEED_LIMIT_NOTE = (
    "**70 mph** roads are mostly motorways and dual carriageways — lower rates may reflect road design, "
    "separation, and access control rather than speed alone. **Unknown / not recorded** speed limits are excluded from the trend line."
)

DATA_MISSING_LABEL = "Data missing or out of range"
UNKNOWN_SPEED_LABEL = "Unknown / not recorded"

VEHICLE_RECORD_CONTEXT = (
    "This page is analysed at **vehicle-record level**. Multi-vehicle collisions may contribute "
    "more than one record, so vehicle counts will exceed collision counts."
)

VEHICLE_EXPOSURE_CAVEAT = (
    "Rates are calculated within **recorded collision vehicle records** and are **not adjusted** "
    "for vehicle miles, fleet size, trip purpose, road exposure, or rider/driver behaviour. "
    "They indicate involvement in serious/fatal collisions — not causation or inherent vehicle risk."
)

MODEL_INVOLVEMENT_CAVEAT = (
    "Model-level rates are **not exposure-adjusted** and do **not** imply vehicle defect, causation, "
    "or inherent model risk. Rankings reflect involvement patterns within STATS19 collision records only."
)

CASE_DRILLDOWN_NOTE = (
    "Case examples show high-scoring vehicle records for context only. They do **not** indicate "
    "liability or causation."
)

INVOLVEMENT_RATE_LABEL = "Serious/fatal involvement rate (%)"

SCORE_DEFINITIONS = (
    "**Triage score** combines darkness, speed limit, rural/urban area, weather, road surface, "
    "vehicle type, and driver age band into a rule-based prioritisation score.\n\n"
    "**Harm score** starts from triage score (×0.5) and adds collision severity weighting plus "
    "skidding, carriageway departure, and off-carriageway impact markers.\n\n"
    "Both scores are internal heuristics — not official STATS19 metrics, legal assessments, or "
    "predictive liability models."
)

DRIVER_AGE_NOTE = (
    "Average age excludes missing or invalid driver-age records."
)
