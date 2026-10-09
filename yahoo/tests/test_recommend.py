from conftest import BENCH, BIG, STAR, WING, player, team

from yahoo.analytics.categories import CATEGORIES
from yahoo.analytics.recommend import recommend_moves
from yahoo.analytics.roles import ROLE_UNVERIFIED
from yahoo.analytics.sim import SimPlayer

MEMO_FIELDS = {
    "action", "delta_win_prob", "delta_expected_category_wins", "per_category_win_rates",
    "assumptions", "role_and_injury_sources", "confidence", "confidence_reasons", "role_flag",
}


def rosters():
    mine = [player(f"m{i}", l, 3) for i, l in enumerate([STAR, WING, WING, BIG, BIG, BENCH, BENCH, BENCH])]
    opp = [player(f"o{i}", l, 3) for i, l in enumerate([STAR, WING, WING, BIG, BIG, WING, BIG, WING])]
    return team("Me", mine), team("Opp", opp)


def test_memo_has_every_required_field_and_ranks_by_win_prob():
    me, opp = rosters()
    cands = [player("fa_good", WING, 4), player("fa_meh", BENCH, 2), player("fa_big", BIG, 4)]
    out = recommend_moves(me, opp, cands, n_sims=4000)
    assert out["memos"]
    deltas = [m["delta_win_prob"] for m in out["memos"]]
    assert deltas == sorted(deltas, reverse=True)
    for m in out["memos"]:
        assert MEMO_FIELDS <= set(m)
        assert set(m["per_category_win_rates"]) == set(CATEGORIES)
        assert m["confidence"] in {"high", "medium", "low"}
        for b in m["role_and_injury_sources"]:
            assert "sources" in b and "role_status" in b


def test_upgrade_over_bench_player_is_positive_and_drops_bench():
    me, opp = rosters()
    out = recommend_moves(me, opp, [player("fa_good", WING, 4)], n_sims=4000)
    top = out["memos"][0]
    assert top["delta_win_prob"] > 0 and top["delta_expected_category_wins"] > 0
    assert top["drop"].startswith("m5") or top["drop"] in {"m5", "m6", "m7"}


def test_unverified_role_is_flagged_and_low_confidence():
    me, opp = rosters()
    c = player("fa_unv", WING, 4, role=ROLE_UNVERIFIED)
    m = recommend_moves(me, opp, [c], n_sims=4000)["memos"][0]
    assert m["role_flag"] == ROLE_UNVERIFIED
    assert m["confidence"] == "low"
    assert any("role unverified" in r for r in m["confidence_reasons"])


def test_player_without_projection_is_not_evaluated_and_marked():
    me, opp = rosters()
    nop = SimPlayer("fa_none", "fa_none", None, [], meta={"reason": "no current-season games"})
    out = recommend_moves(me, opp, [nop], n_sims=2000)
    assert out["memos"] == []
    assert out["not_evaluated"][0]["role_status"] == ROLE_UNVERIFIED


def test_protected_players_are_never_dropped():
    me, opp = rosters()
    protect = {p.key for p in me.players if p.key != "m0"}
    m = recommend_moves(me, opp, [player("fa_good", WING, 4)], n_sims=2000, protect=protect)["memos"][0]
    assert m["drop"] == "m0"


def test_high_confidence_requires_clear_verified_effect():
    me, opp = rosters()
    m = recommend_moves(me, opp, [player("fa_star", STAR, 4)], n_sims=4000)["memos"][0]
    assert m["confidence"] == "high", m["confidence_reasons"]
