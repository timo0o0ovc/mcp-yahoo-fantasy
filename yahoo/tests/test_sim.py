import numpy as np
import pytest
from conftest import BENCH, BIG, STAR, WING, player, team

from yahoo.analytics.categories import CATEGORIES, TOTAL_FIELDS
from yahoo.analytics.sim import DEFAULT_SIMS, compare, draw_player, sim_matchup, team_totals


def totals(**kw):
    base = {f: np.array([0.0]) for f in TOTAL_FIELDS}
    base.update({k: np.array([float(v)]) for k, v in kw.items()})
    return base


def test_default_is_10k_runs(balanced_roster):
    assert DEFAULT_SIMS == 10_000
    res = sim_matchup(team("A", balanced_roster("a")), team("B", balanced_roster("b")))
    assert res["n_sims"] == 10_000
    assert set(res["categories"]) == set(CATEGORIES) and len(CATEGORIES) == 9


def test_equal_teams_are_a_coin_flip(balanced_roster):
    res = sim_matchup(team("A", balanced_roster("a")), team("B", balanced_roster("b")))
    assert abs(res["win_prob"] - res["loss_prob"]) < 0.04
    assert abs(res["expected_category_wins"] - 4.5) < 0.12
    for cat, r in res["categories"].items():
        assert abs(r["win"] - r["loss"]) < 0.05, cat


def test_fg_pct_is_summed_makes_over_summed_attempts():
    # A: 10/20 = .500. B: players at 1/1 (1.000) and 9/21 (.429).
    # Averaging B's percentages gives .714 (B "wins"); true team FG% is 10/22 = .455.
    a = totals(FGM=10, FGA=20)
    b = totals(FGM=1 + 9, FGA=1 + 21)
    res = compare(a, b)
    assert res["categories"]["FG%"]["win"] == 1.0
    assert res["categories"]["FG%"]["mean_b"] == pytest.approx(0.455, abs=1e-3)


def test_ft_pct_from_makes_and_attempts():
    res = compare(totals(FTM=8, FTA=10), totals(FTM=15, FTA=20))  # .800 vs .750
    assert res["categories"]["FT%"]["win"] == 1.0


def test_turnovers_lower_is_better():
    res = compare(totals(TOV=10), totals(TOV=20))
    assert res["categories"]["TO"]["win"] == 1.0
    res = compare(totals(TOV=20, PTS=50), totals(TOV=10, PTS=40))
    assert res["categories"]["TO"]["loss"] == 1.0
    assert res["categories"]["PTS"]["win"] == 1.0


def test_turnover_heavy_roster_loses_to_in_simulation():
    sloppy = dict(WING, TOV=4.0)
    a = team("A", [player(f"a{i}", sloppy, 3) for i in range(8)])
    b = team("B", [player(f"b{i}", WING, 3) for i in range(8)])
    res = sim_matchup(a, b)
    assert res["categories"]["TO"]["win"] < 0.05
    assert res["categories"]["TO"]["loss"] > 0.9


def test_percentage_ties_counted_as_ties():
    res = compare(totals(FGM=5, FGA=10, FTM=0, FTA=0), totals(FGM=10, FGA=20, FTM=0, FTA=0))
    assert res["categories"]["FG%"]["tie"] == 1.0
    assert res["categories"]["FT%"]["tie"] == 1.0


def test_stronger_team_wins_most_weeks(balanced_roster):
    strong = team("A", [player(f"a{i}", STAR, 4) for i in range(10)])
    weak = team("B", [player(f"b{i}", BENCH, 3) for i in range(10)])
    res = sim_matchup(strong, weak)
    assert res["win_prob"] > 0.95
    assert res["expected_category_wins"] > 6.5


def test_more_games_helps_counting_stats():
    four = team("A", [player(f"a{i}", WING, 4) for i in range(8)])
    two = team("B", [player(f"b{i}", WING, 2) for i in range(8)])
    res = sim_matchup(four, two)
    for cat in ("PTS", "REB", "AST", "3PM"):
        assert res["categories"][cat]["win"] > 0.9, cat


def test_week_to_date_actuals_are_added():
    a = team("A", [player("a", WING, 1)], actuals={"PTS": 500})
    b = team("B", [player("b", WING, 1)])
    assert sim_matchup(a, b)["categories"]["PTS"]["win"] == 1.0


def test_seeded_runs_are_reproducible(balanced_roster):
    a, b = team("A", balanced_roster("a")), team("B", balanced_roster("b"))
    assert sim_matchup(a, b, seed=7)["win_prob"] == sim_matchup(a, b, seed=7)["win_prob"]


def test_draws_are_internally_consistent():
    d = draw_player(player("x", STAR, 4), 5000, 1)
    assert np.all(d["FG3M"] <= d["FGM"]) and np.all(d["FGM"] <= d["FGA"])
    assert np.all(d["FTM"] <= d["FTA"])
    assert np.array_equal(d["PTS"], 2 * d["FGM"] + d["FG3M"] + d["FTM"])
    assert d["PTS"].mean() == pytest.approx(STAR["PTS"], rel=0.08)
    assert (d["FGM"].sum() / d["FGA"].sum()) == pytest.approx(0.5, abs=0.03)


def test_out_player_contributes_nothing():
    t = team("A", [player("x", STAR, 3, p_play=0.0)])
    tot = team_totals(t, 1000, 3)
    assert tot["PTS"].sum() == 0


def test_daily_slot_cap_limits_games_counted():
    roster = [player(f"p{i}", WING, 1) for i in range(12)]
    capped = team_totals(team("A", roster, active_slots=10), 2000, 5)
    uncapped = team_totals(team("A", roster), 2000, 5)
    assert capped["PTS"].mean() < uncapped["PTS"].mean()
    assert capped["PTS"].mean() == pytest.approx(uncapped["PTS"].mean() * 10 / 12, rel=0.06)


def test_common_random_numbers_make_identical_swaps_zero():
    roster = [player(f"p{i}", BIG, 3) for i in range(6)]
    opp = team("B", [player(f"o{i}", BIG, 3) for i in range(6)])
    r1 = sim_matchup(team("A", roster), opp, seed=11)
    r2 = sim_matchup(team("A", list(reversed(roster))), opp, seed=11)
    assert r1["win_prob"] == r2["win_prob"]
