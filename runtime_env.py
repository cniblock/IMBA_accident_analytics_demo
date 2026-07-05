"""Runtime detection for local Streamlit vs Streamlit in Snowflake."""

from __future__ import annotations

import os


def is_snowflake_streamlit() -> bool:
    """Return True when the app runs inside Streamlit in Snowflake (SiS)."""
    if os.environ.get("IMBA_SNOWFLAKE_RUNTIME", "").strip().lower() in {"1", "true", "yes"}:
        return True
    if os.path.isfile("/snowflake/session/token"):
        return True
    try:
        from snowflake.snowpark.context import get_active_session

        get_active_session()
        return True
    except Exception:
        return False
