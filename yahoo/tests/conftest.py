import datetime as dt

import pytest

from yahoo.analytics.sim import SimPlayer, SimTeam

WEEK = [dt.date(2026, 10, 26) + dt.timedelta(days=i) for i in range(7)]

# Synthetic per-game lines (illustrative only, not real players).
STAR = {"MIN": 36, "FGM": 10, "FGA": 20, "FG3M": 3, "FG3A": 8, "FTM": 6, "FTA": 7,
        "PTS": 29, "REB": 8, "AST": 8, "STL": 1.3, "BLK": 0.6, "TOV": 3.5}
WING = {"MIN": 32, "FGM": 6, "FGA": 13, "FG3M": 2.2, "FG3A": 6, "FTM": 2.5, "FTA": 3,
        "PTS": 16.7, "REB": 5, "AST": 3, "STL": 1.1, "BLK": 0.5, "TOV": 1.6}
BIG = {"MIN": 30, "FGM": 6, "FGA": 10, "FG3M": 0.3, "FG3A": 1, "FTM": 2.5, "FTA": 4,
       "PTS": 14.8, "REB": 10, "AST": 2, "STL": 0.7, "BLK": 1.8, "TOV": 1.8}
BENCH = {"MIN": 18, "FGM": 2.5, "FGA": 6, "FG3M": 0.8, "FG3A": 2.5, "FTM": 0.8, "FTA": 1,
         "PTS": 6.6, "REB": 2.5, "AST": 1.5, "STL": 0.5, "BLK": 0.2, "TOV": 0.8}


def player(key, line, n_games=3, p_play=1.0, sample=20, role="verified", **meta):
    m = {"role": {"label": role, "team": "TST", "sources": [], "unverified_reasons": []},
         "games_used": sample, "preseason_used": False, "assumptions": []}
    m.update(meta)
    return SimPlayer(key, key, dict(line), WEEK[:n_games], p_play, sample, m)


@pytest.fixture
def make_player():
    return player


@pytest.fixture
def balanced_roster():
    def build(prefix):
        lines = [STAR, WING, WING, BIG, BIG, BENCH, BENCH, WING, BIG, BENCH]
        return [player(f"{prefix}{i}", l, 3) for i, l in enumerate(lines)]

    return build


def team(name, players, **kw):
    return SimTeam(name, players, **kw)
