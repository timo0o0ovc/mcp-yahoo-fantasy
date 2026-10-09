"""9-category head-to-head definitions."""

# Display order matches Yahoo's scoreboard.
CATEGORIES = ("FG%", "FT%", "3PM", "PTS", "REB", "AST", "STL", "BLK", "TO")

# Categories where the lower total wins.
LOWER_IS_BETTER = frozenset({"TO"})

# Percentage categories are computed from summed makes / summed attempts, never by
# averaging per-player or per-game percentages.
RATIO_CATEGORIES = {"FG%": ("FGM", "FGA"), "FT%": ("FTM", "FTA")}

# Raw counting totals the simulator tracks per team.
TOTAL_FIELDS = ("FGM", "FGA", "FTM", "FTA", "FG3M", "PTS", "REB", "AST", "STL", "BLK", "TOV")

COUNTING_FIELD = {
    "3PM": "FG3M",
    "PTS": "PTS",
    "REB": "REB",
    "AST": "AST",
    "STL": "STL",
    "BLK": "BLK",
    "TO": "TOV",
}

# Yahoo displays percentages to three decimals; equal displayed values are a tie.
PCT_DECIMALS = 3
