"""
Read-only analytics for Yahoo 9-category head-to-head NBA leagues.

Pure functions (no network; testable with fixtures):
  sim_matchup        Monte Carlo (10k runs default) of one week's matchup
  player_projection  per-game line from the last 14/30 days of current-season logs
  games_this_week    games per NBA team in a Yahoo week, from the official schedule
  recommend_moves    ranked add/drop decision memos

`service` wires these to live Yahoo + nba_api data for the MCP tools.
"""

from .categories import CATEGORIES, LOWER_IS_BETTER
from .projection import manual_projection, player_projection
from .recommend import recommend_moves
from .roles import FRESHNESS_DAYS, ROLE_UNVERIFIED, Evidence, check_role
from .schedule import games_this_week
from .sim import DEFAULT_SIMS, SimPlayer, SimTeam, sim_matchup

__all__ = [
    "CATEGORIES",
    "DEFAULT_SIMS",
    "FRESHNESS_DAYS",
    "LOWER_IS_BETTER",
    "ROLE_UNVERIFIED",
    "Evidence",
    "SimPlayer",
    "SimTeam",
    "check_role",
    "games_this_week",
    "manual_projection",
    "player_projection",
    "recommend_moves",
    "sim_matchup",
]
