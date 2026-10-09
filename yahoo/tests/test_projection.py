import datetime as dt

import pytest

from yahoo.analytics.projection import current_season, manual_projection, player_projection
from yahoo.analytics.roles import ROLE_UNVERIFIED, Evidence, check_role

AS_OF = dt.date(2026, 12, 1)


def row(days_ago, season="2026-27", stype="Regular Season", pts=20, mins=30, team="OKC"):
    d = AS_OF - dt.timedelta(days=days_ago)
    return {
        "SEASON_YEAR": season, "SEASON_TYPE": stype, "GAME_DATE": d.isoformat() + "T00:00:00",
        "TEAM_ABBREVIATION": team, "MIN": mins, "FGM": 8, "FGA": 16, "FG3M": 2, "FG3A": 5,
        "FTM": 2, "FTA": 2, "PTS": pts, "REB": 5, "AST": 4, "STL": 1, "BLK": 1, "TOV": 2,
    }


def fresh_status():
    return [Evidence("injury", "healthy", "Yahoo player status", AS_OF)]


def test_season_string():
    assert current_season(dt.date(2026, 10, 9)) == "2026-27"
    assert current_season(dt.date(2027, 3, 1)) == "2026-27"


def test_windows_are_14_and_30_days_and_blended():
    rows = [row(d, pts=30) for d in (1, 3, 5)] + [row(d, pts=10) for d in (20, 22, 25)]
    p = player_projection(rows, AS_OF, evidence=fresh_status())
    assert p.windows[14]["games"] == 3 and p.windows[30]["games"] == 6
    assert p.windows[14]["per_game"]["PTS"] == 30
    assert p.windows[30]["per_game"]["PTS"] == 20
    assert p.per_game["PTS"] == pytest.approx(0.6 * 30 + 0.4 * 20)


def test_last_season_rows_are_never_used():
    rows = [row(2, season="2025-26", pts=40), row(5, season="2025-26", pts=40)]
    p = player_projection(rows, AS_OF, evidence=fresh_status())
    assert p.status == "no_recent_games" and p.per_game is None
    assert p.role.label == ROLE_UNVERIFIED
    assert any("other seasons" in a for a in p.assumptions)


def test_games_older_than_30_days_are_ignored():
    rows = [row(31, pts=50), row(45, pts=50), row(10, pts=12)]
    p = player_projection(rows, AS_OF, evidence=fresh_status())
    assert p.games_used == 1 and p.per_game["PTS"] == 12


def test_preseason_only_used_when_too_few_regular_games_and_flagged():
    rows = [row(d, stype="Pre Season", mins=20) for d in (2, 4, 6)]
    p = player_projection(rows, AS_OF, evidence=fresh_status())
    assert p.preseason_used and p.status == "ok"
    assert any("preseason" in a.lower() for a in p.assumptions)

    rows += [row(d) for d in (1, 3, 5)]
    p = player_projection(rows, AS_OF, evidence=fresh_status())
    assert not p.preseason_used and p.games_used == 3


def test_role_verified_needs_recent_games_team_and_injury_source():
    rows = [row(3), row(6)]
    assert player_projection(rows, AS_OF, evidence=fresh_status()).role.label == "verified"
    no_injury = player_projection(rows, AS_OF).role
    assert no_injury.label == ROLE_UNVERIFIED
    assert any("injury" in r for r in no_injury.unverified_reasons)


def test_role_unverified_when_last_game_older_than_14_days():
    p = player_projection([row(20), row(25)], AS_OF, evidence=fresh_status())
    assert p.status == "ok"  # 30-day window still projects
    assert p.role.label == ROLE_UNVERIFIED


def test_stale_evidence_does_not_count():
    old = [Evidence("role", "starter", "beat report", AS_OF - dt.timedelta(days=15)),
           Evidence("injury", "healthy", "Yahoo", AS_OF - dt.timedelta(days=15)),
           Evidence("team", "OKC", "news", AS_OF - dt.timedelta(days=15))]
    rc = check_role(AS_OF, [], old)
    assert rc.label == ROLE_UNVERIFIED and len(rc.unverified_reasons) == 3
    assert all(not s["fresh"] for s in rc.sources)


def test_dated_news_can_verify_role_without_games():
    ev = [Evidence("role", "starting PF", "team beat report", AS_OF - dt.timedelta(days=2)),
          Evidence("team", "SAS", "stats.nba.com", AS_OF),
          Evidence("injury", "healthy", "Yahoo player status", AS_OF)]
    rc = check_role(AS_OF, [], ev)
    assert rc.label == "verified" and rc.team == "SAS"
    assert {s["date"] for s in rc.sources} <= {AS_OF.isoformat(), (AS_OF - dt.timedelta(days=2)).isoformat()}


def test_projected_minutes_rescales_per_minute_rates():
    rows = [row(d, mins=20, pts=10) for d in (1, 2, 3)]
    p = player_projection(rows, AS_OF, evidence=fresh_status(), projected_minutes=30)
    assert p.per_game["MIN"] == 30 and p.per_game["PTS"] == pytest.approx(15)


def test_manual_line_is_labelled_assumption():
    p = manual_projection("Rookie", {"PTS": 12, "FGA": 10, "FGM": 4.5}, "analyst note", AS_OF, AS_OF)
    assert p.status == "ok" and "assumption" in p.assumptions[0]
    assert p.role.label == ROLE_UNVERIFIED
