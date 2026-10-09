"""
Games per NBA team inside a Yahoo scoring week.

Input rows are shaped like nba_api ScheduleLeagueV2 'SeasonGames' rows. Only regular-
season games count (game ids starting "002"): preseason ("001"), All-Star ("003"),
playoffs ("004"), play-in ("005") and the NBA Cup final ("006", which does not count
toward regular-season stats) are excluded.
"""

from collections import defaultdict

from .roles import to_date

REGULAR_SEASON_PREFIX = "002"


def regular_season_games(rows):
    return [r for r in rows if str(r.get("gameId", "")).startswith(REGULAR_SEASON_PREFIX)]


def _game_date(r):
    # gameDateEst is the local US date the game is played on, which is what Yahoo uses.
    return to_date(r.get("gameDateEst") or r.get("gameDate"))


def team_game_dates(rows, start, end, from_date=None):
    """{tricode: [date, ...]} for regular-season games in [max(start, from_date), end]."""
    start, end = to_date(start), to_date(end)
    lo = max(start, to_date(from_date)) if from_date else start
    out = defaultdict(list)
    for r in regular_season_games(rows):
        d = _game_date(r)
        if lo <= d <= end:
            for side in ("homeTeam_teamTricode", "awayTeam_teamTricode"):
                out[r[side]].append(d)
    return {t: sorted(ds) for t, ds in out.items()}


def games_this_week(rows, start, end, from_date=None, teams=None, fetched_at=None):
    """
    Summarise games per team for a Yahoo week.

    Returns per-team totals for the whole week and remaining from `from_date`, plus the
    teams with 4+ games and games-per-day (for daily lineup congestion).
    """
    full = team_game_dates(rows, start, end)
    remaining = team_game_dates(rows, start, end, from_date) if from_date else full
    all_teams = sorted(set(teams)) if teams else sorted(full)

    per_day = defaultdict(int)
    for r in regular_season_games(rows):
        d = _game_date(r)
        if to_date(start) <= d <= to_date(end):
            per_day[d.isoformat()] += 1

    by_team = {
        t: {
            "games": len(full.get(t, [])),
            "remaining": len(remaining.get(t, [])),
            "dates": [d.isoformat() for d in full.get(t, [])],
            "remaining_dates": [d.isoformat() for d in remaining.get(t, [])],
        }
        for t in all_teams
    }
    return {
        "week_start": to_date(start).isoformat(),
        "week_end": to_date(end).isoformat(),
        "from_date": to_date(from_date).isoformat() if from_date else None,
        "teams": by_team,
        "four_plus_game_teams": sorted(t for t, v in by_team.items() if v["games"] >= 4),
        "games_per_day": dict(sorted(per_day.items())),
        "source": "NBA official schedule (stats.nba.com scheduleleaguev2)",
        "source_fetched_at": fetched_at,
    }
