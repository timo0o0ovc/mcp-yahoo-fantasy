"""End-to-end wiring of the live tools with a fake Yahoo client and stubbed nba_api."""

import datetime as dt

import pytest

from yahoo.analytics import nba_data, service

TODAY = dt.date(2026, 10, 27)
START, END = dt.date(2026, 10, 26), dt.date(2026, 11, 1)
TEAMS = {"Alpha One": "OKC", "Alpha Two": "MIA", "Beta One": "DEN", "Beta Two": "LAL",
         "Free Wing": "OKC", "Rookie Guy": "SAS", "Ghost Player": "BOS"}
IDS = {n: i for i, n in enumerate(TEAMS, 1)}


def _log(pid, days_ago, season="2026-27"):
    d = TODAY - dt.timedelta(days=days_ago)
    return {"SEASON_YEAR": season, "SEASON_TYPE": "Regular Season", "GAME_DATE": d.isoformat(),
            "TEAM_ABBREVIATION": TEAMS[[n for n, i in IDS.items() if i == pid][0]], "MIN": 32,
            "FGM": 7, "FGA": 15, "FG3M": 2, "FG3A": 6, "FTM": 3, "FTA": 4, "PTS": 19,
            "REB": 6, "AST": 4, "STL": 1, "BLK": 0.5, "TOV": 2}


SCHEDULE = [
    {"gameId": "0022600001", "gameDateEst": "2026-10-28", "homeTeam_teamTricode": "OKC", "awayTeam_teamTricode": "DEN"},
    {"gameId": "0022600002", "gameDateEst": "2026-10-30", "homeTeam_teamTricode": "MIA", "awayTeam_teamTricode": "LAL"},
    {"gameId": "0022600003", "gameDateEst": "2026-10-31", "homeTeam_teamTricode": "OKC", "awayTeam_teamTricode": "LAL"},
    {"gameId": "0022600004", "gameDateEst": "2026-10-26", "homeTeam_teamTricode": "MIA", "awayTeam_teamTricode": "DEN"},
]


@pytest.fixture(autouse=True)
def stub_nba(monkeypatch):
    def logs(pid, season, as_of, days=30):
        if pid == IDS["Ghost Player"]:
            return [_log(pid, 3, season="2025-26")]  # last season only
        if pid == IDS["Rookie Guy"]:
            return []
        return [_log(pid, d) for d in (1, 3, 5, 8, 12, 20)]

    directory = [{"id": IDS[n], "name": n, "team": t, "roster_status": 1} for n, t in TEAMS.items()]
    monkeypatch.setattr(nba_data, "fetch_game_logs", logs)
    monkeypatch.setattr(nba_data, "fetch_schedule", lambda s: (SCHEDULE, TODAY.isoformat()))
    monkeypatch.setattr(nba_data, "player_directory", lambda s: (directory, TODAY.isoformat()))
    monkeypatch.setattr(service, "us_today", lambda: TODAY)


def yp(pid, name, pos="UTIL", status=""):
    return {"player_id": pid, "name": name, "status": status, "selected_position": pos}


class FakeTeam:
    def __init__(self, key):
        self.key = key

    def matchup(self, week):
        return "t.2" if self.key == "t.1" else "t.1"

    def roster(self, day=None):
        if self.key == "t.1":
            return [yp(1, "Alpha One"), yp(2, "Alpha Two"), yp(7, "Ghost Player", "IL")]
        return [yp(3, "Beta One"), yp(4, "Beta Two", status="GTD")]


class FakeLeague:
    def current_week(self):
        return 1

    def week_date_range(self, week):
        return START, END

    def positions(self):
        return {"PG": {"count": 1}, "UTIL": {"count": 2}, "BN": {"count": 3}, "IL": {"count": 2}}

    def matchups(self, week):
        return {"fantasy_content": {"league": [{}, {"scoreboard": {}}]}}

    def free_agents(self, pos):
        return [{"player_id": 5, "name": "Free Wing", "percent_owned": 40, "status": ""},
                {"player_id": 6, "name": "Rookie Guy", "percent_owned": 30, "status": ""},
                {"player_id": 8, "name": "Ghost Player", "percent_owned": 5, "status": ""}]


class FakeClient:
    def league(self, key=None):
        return FakeLeague()

    def team_key(self, team_key=None, league_key=None):
        return team_key or "t.1"

    def team(self, key=None, league_key=None):
        return FakeTeam(key or "t.1")


def test_games_this_week_live():
    out = service.games_this_week_live(FakeClient(), week=1)
    assert out["teams"]["OKC"]["games"] == 2 and out["teams"]["MIA"]["remaining"] == 1


def test_sim_matchup_live_end_to_end():
    out = service.sim_matchup_live(FakeClient(), week=1, n_sims=2000)
    assert 0 <= out["win_prob"] <= 1 and out["active_slots_per_day"] == 3
    assert any("IL slot" in n for n in out["roster_notes"])
    roles = {p["name"]: p for p in out["players"]["t.1"]}
    assert roles["Alpha One"]["role_status"] == "verified"
    assert out["simulated_from"] == TODAY.isoformat()


def test_recommend_moves_live_flags_unverified_and_never_uses_last_season():
    out = service.recommend_moves_live(FakeClient(), week=1, n_sims=2000, positions=("PG",))
    names = {m["add"] for m in out["memos"]}
    assert "Free Wing" in names
    skipped = {x["player"]: x for x in out["not_evaluated"]}
    assert "Ghost Player" in skipped and "Rookie Guy" in skipped  # no current-season games
    assert all(x["role_status"] == "role unverified" for x in skipped.values())


def test_manual_line_lets_rookie_be_evaluated_but_low_confidence():
    manual = {"Rookie Guy": {"FGM": 5, "FGA": 11, "FG3M": 1.5, "FG3A": 4, "FTM": 2, "FTA": 3,
                             "PTS": 13.5, "REB": 4, "AST": 3, "STL": 1, "BLK": 0.4, "TOV": 1.5,
                             "MIN": 26, "source": "analyst estimate", "date": "2026-10-25"}}
    out = service.recommend_moves_live(FakeClient(), week=1, n_sims=2000, positions=("PG",),
                                       candidate_names=["Rookie Guy"], manual_lines=manual)
    m = out["memos"][0]
    assert m["add"] == "Rookie Guy" and m["confidence"] == "low"
    assert any("Manual line" in a for a in m["assumptions"])
