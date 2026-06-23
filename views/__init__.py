"""Dashboard view modules."""

from views.casualty_intelligence import page_casualty_intelligence
from views.executive_overview import page_executive_overview
from views.georisk_map import page_georisk_map
from views.pipeline_health import page_pipeline_health
from views.risk_factors import page_risk_factors
from views.sidebar import (
    INTELLIGENCE_PAGES,
    apply_sidebar_filters,
    render_active_filter_banner,
    render_intelligence_nav,
    render_sidebar_logo,
)
from views.vehicle_intelligence import page_vehicle_intelligence

__all__ = [
    "INTELLIGENCE_PAGES",
    "apply_sidebar_filters",
    "render_active_filter_banner",
    "render_intelligence_nav",
    "render_sidebar_logo",
    "page_casualty_intelligence",
    "page_executive_overview",
    "page_georisk_map",
    "page_pipeline_health",
    "page_risk_factors",
    "page_vehicle_intelligence",
]
