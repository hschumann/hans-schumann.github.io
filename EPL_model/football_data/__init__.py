"""Football-Data.co.uk EPL match and odds data."""

from football_data.columns import (
    COLUMN_GROUPS,
    PREMATCH_COLUMNS,
    POSTMATCH_COLUMNS,
    list_columns,
)
from football_data.loader import load_epl_matches, load_fixtures

__all__ = [
    "COLUMN_GROUPS",
    "PREMATCH_COLUMNS",
    "POSTMATCH_COLUMNS",
    "list_columns",
    "load_epl_matches",
    "load_fixtures",
]
