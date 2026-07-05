"""One-off script to extract page functions from app.py into views/."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
app_lines = (ROOT / "app.py").read_text(encoding="utf-8").splitlines(keepends=True)

sections = {
    "views/sidebar.py": (
        46,
        152,
        '''"""Sidebar filters and active-filter banner."""

import base64
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

from config import CODE_MAPS
from data_loading import resolve_district_display as _resolve_district_display
from transforms import as_int_if_possible as _as_int_if_possible

ROOT = Path(__file__).resolve().parent.parent

''',
    ),
    "views/executive_overview.py": (
        155,
        406,
        '''"""Executive Overview page."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from views.constants import HARM_INDEX_CAPTION

''',
    ),
    "views/georisk_map.py": (
        409,
        503,
        '''"""GeoRisk Map page."""

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from transforms import ensure_label_columns as _ensure_label_columns, series_or_default as _series_or_default
from views.constants import HARM_INDEX_CAPTION

''',
    ),
    "views/risk_factors.py": (
        506,
        925,
        '''"""Risk Factors page."""

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from transforms import ensure_label_columns as _ensure_label_columns, safe_ratio as _safe_ratio, series_or_default as _series_or_default

''',
    ),
    "views/vehicle_intelligence.py": (
        928,
        1589,
        '''"""Vehicle Intelligence page."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from transforms import (
    add_vehicle_intelligence_features as _add_vehicle_intelligence_features,
    collision_level_serious_fatal_stats as _collision_level_serious_fatal_stats,
    safe_ratio as _safe_ratio,
)
from views.constants import TRIAGE_HARM_CAPTION

''',
    ),
    "views/casualty_intelligence.py": (
        1591,
        2223,
        '''"""Casualty Intelligence page."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data_loading import add_district_labels as _add_district_labels
from transforms import (
    REQUIRED_CASUALTY_VIEW_COLUMNS,
    casualty_priority_reason,
    casualty_priority_score,
    ensure_label_columns as _ensure_label_columns,
    safe_ratio as _safe_ratio,
    series_or_default as _series_or_default,
    validate_schema as _validate_schema,
)
from views.constants import PRIORITY_QUEUE_CAPTION

''',
    ),
    "views/pipeline_health.py": (
        2225,
        2300,
        '''"""Data Quality and Refresh Status page."""

import pandas as pd
import streamlit as st

from config import CODE_MAPS
from data_loading import has_provisional_data

''',
    ),
}

(ROOT / "views").mkdir(exist_ok=True)
for rel_path, (start, end, header) in sections.items():
    body = "".join(app_lines[start - 1 : end])
    (ROOT / rel_path).write_text(header + body, encoding="utf-8")
    print(f"Wrote {rel_path}")
