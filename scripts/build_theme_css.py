"""Regenerate styles/theme.css from styles/theme.py colour tokens."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from styles.theme import THEME_CSS_PATH, _css  # noqa: E402


def main() -> None:
    THEME_CSS_PATH.write_text(_css(), encoding="utf-8")
    print(f"Wrote {THEME_CSS_PATH} ({THEME_CSS_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
