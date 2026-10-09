from yahoo.analytics.schedule import games_this_week
from yahoo.analytics.yahoo_parse import week_totals


def g(gid, date, home, away):
    return {"gameId": gid, "gameDateEst": f"{date}T00:00:00Z", "homeTeam_teamTricode": home,
            "awayTeam_teamTricode": away}


ROWS = [
    g("0012600050", "2026-10-15", "OKC", "DEN"),  # preseason: excluded
    g("0022600001", "2026-10-26", "OKC", "DEN"),
    g("0022600010", "2026-10-28", "MIA", "OKC"),
    g("0022600020", "2026-10-30", "OKC", "LAL"),
    g("0022600030", "2026-11-01", "SAC", "OKC"),
    g("0022600031", "2026-11-01", "MIA", "DEN"),
    g("0062600001", "2026-10-29", "OKC", "MIA"),  # Cup final id: excluded
    g("0022600040", "2026-11-02", "OKC", "MIA"),  # next week
]


def test_counts_regular_season_games_in_week():
    out = games_this_week(ROWS, "2026-10-26", "2026-11-01")
    assert out["teams"]["OKC"]["games"] == 4
    assert out["teams"]["MIA"]["games"] == 2
    assert out["teams"]["DEN"]["games"] == 2
    assert out["four_plus_game_teams"] == ["OKC"]
    assert out["games_per_day"]["2026-11-01"] == 2


def test_remaining_from_date():
    out = games_this_week(ROWS, "2026-10-26", "2026-11-01", from_date="2026-10-29")
    assert out["teams"]["OKC"]["remaining"] == 2
    assert out["teams"]["OKC"]["remaining_dates"] == ["2026-10-30", "2026-11-01"]


def test_team_filter():
    out = games_this_week(ROWS, "2026-10-26", "2026-11-01", teams=["MIA"])
    assert list(out["teams"]) == ["MIA"]


def _scoreboard(team_key, stats):
    return {"fantasy_content": {"league": [{"league_key": "x"}, {"scoreboard": {"0": {"matchups": {
        "0": {"matchup": {"0": {"teams": {"0": {"team": [
            [{"team_key": team_key}, {"name": "T"}],
            {"team_stats": {"coverage_type": "week", "stats": [
                {"stat": {"stat_id": k, "value": v}} for k, v in stats.items()]}},
        ]}}}}}}}}}]}}


def test_week_totals_rebuild_percentages_from_makes_and_attempts():
    raw = _scoreboard("466.l.1.t.2", {"9004003": "120/250", "5": ".480", "9007006": "40/50",
                                       "8": ".800", "10": "30", "12": "310", "15": "140",
                                       "16": "70", "17": "20", "18": "15", "19": "35"})
    t = week_totals(raw, "466.l.1.t.2")
    assert t == {"FGM": 120, "FGA": 250, "FTM": 40, "FTA": 50, "FG3M": 30, "PTS": 310,
                 "REB": 140, "AST": 70, "STL": 20, "BLK": 15, "TOV": 35}
    assert week_totals(raw, "466.l.1.t.9") is None


def test_week_totals_before_games_are_zero():
    t = week_totals(_scoreboard("k", {"9004003": "-/-", "12": "-"}), "k")
    assert t["FGA"] == 0 and t["PTS"] == 0
