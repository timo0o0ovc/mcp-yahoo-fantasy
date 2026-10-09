"""
Rank add/drop moves by their effect on this week's matchup.

Each candidate free agent is tried against every droppable player on your roster with
common random numbers, so the change in win probability isolates the move itself. The
best drop per candidate becomes one decision memo. Memos are ranked by the change in
matchup-win probability, then by the change in expected category wins.
"""

from dataclasses import replace

import numpy as np

from .categories import CATEGORIES
from .roles import ROLE_UNVERIFIED
from .sim import DEFAULT_SIMS, SimTeam, public, sim_matchup

HIGH_SAMPLE_GAMES = 8
LOW_SAMPLE_GAMES = 3


def _role_block(p):
    role = p.meta.get("role") or {}
    return {
        "player": p.name,
        "role_status": role.get("label", ROLE_UNVERIFIED),
        "team": role.get("team"),
        "minutes_14d": role.get("minutes_14d"),
        "injury_status": role.get("injury_status"),
        "unverified_reasons": role.get("unverified_reasons", ["no role check supplied"]),
        "sources": role.get("sources", []),
        "games_in_projection": p.meta.get("games_used", p.sample_games),
        "preseason_used": p.meta.get("preseason_used", False),
        "remaining_games": len(p.game_dates),
        "availability_per_game": p.p_play,
    }


def _confidence(blocks, delta, se):
    reasons = []
    unverified = [b["player"] for b in blocks if b["role_status"] == ROLE_UNVERIFIED]
    if unverified:
        reasons.append("role unverified: " + ", ".join(unverified))
    pre = [b["player"] for b in blocks if b["preseason_used"]]
    if pre:
        reasons.append("preseason data in projection: " + ", ".join(pre))
    min_games = min(b["games_in_projection"] for b in blocks)
    if min_games < LOW_SAMPLE_GAMES:
        reasons.append(f"small sample ({min_games} games)")
    noisy = abs(delta) <= 2 * se
    if noisy:
        reasons.append(f"effect within 2 standard errors (±{2 * se:.3f})")

    if unverified or noisy or min_games < LOW_SAMPLE_GAMES:
        return "low", reasons
    if pre or min_games < HIGH_SAMPLE_GAMES:
        if min_games < HIGH_SAMPLE_GAMES:
            reasons.append(f"moderate sample ({min_games} games)")
        return "medium", reasons
    return "high", reasons or ["all roles verified, adequate sample, effect clear of noise"]


def recommend_moves(
    my_team,
    opponent,
    candidates,
    n_sims=DEFAULT_SIMS,
    seed=20261009,
    protect=(),
    max_memos=10,
    extra_assumptions=(),
):
    """
    my_team / opponent: SimTeam. candidates: SimPlayer free agents with their own
    remaining game dates. protect: player keys never to drop.

    Returns {"baseline", "memos" (ranked), "not_evaluated", "assumptions"}.
    """
    cache = {}
    base = sim_matchup(my_team, opponent, n_sims, seed, cache)
    protect = set(protect)
    droppable = [p for p in my_team.players if p.key not in protect]

    memos, not_evaluated = [], []
    for c in candidates:
        if not c.per_game:
            not_evaluated.append(
                {
                    "player": c.name,
                    "role_status": ROLE_UNVERIFIED,
                    "reason": c.meta.get("reason", "no current-season games in the last 30 days"),
                }
            )
            continue
        trials = []
        for d in droppable:
            team = replace(my_team, players=[p for p in my_team.players if p.key != d.key] + [c])
            res = sim_matchup(team, opponent, n_sims, seed, cache)
            paired = res["_won"].astype(float) - base["_won"].astype(float)
            trials.append((d, res, float(paired.mean()), float(paired.std(ddof=1) / np.sqrt(n_sims))))
        if not trials:
            continue
        trials.sort(key=lambda t: (t[2], t[1]["expected_category_wins"]), reverse=True)
        d, res, delta, se = trials[0]
        blocks = [_role_block(c), _role_block(d)]
        conf, why = _confidence(blocks, delta, se)
        d_cats = res["expected_category_wins"] - base["expected_category_wins"]
        memos.append(
            {
                "action": f"Add {c.name}, drop {d.name}",
                "add": c.name,
                "drop": d.name,
                "delta_win_prob": round(delta, 4),
                "win_prob_before": base["win_prob"],
                "win_prob_after": res["win_prob"],
                "delta_win_prob_std_error": round(se, 4),
                "delta_expected_category_wins": round(d_cats, 3),
                "expected_category_wins_before": base["expected_category_wins"],
                "expected_category_wins_after": res["expected_category_wins"],
                "per_category_win_rates": {
                    cat: {
                        "before": base["categories"][cat]["win"],
                        "after": res["categories"][cat]["win"],
                        "delta": round(res["categories"][cat]["win"] - base["categories"][cat]["win"], 4),
                    }
                    for cat in CATEGORIES
                },
                "remaining_games_added_minus_dropped": len(c.game_dates) - len(d.game_dates),
                "role_and_injury_sources": blocks,
                "role_flag": ROLE_UNVERIFIED
                if any(b["role_status"] == ROLE_UNVERIFIED for b in blocks)
                else "verified",
                "confidence": conf,
                "confidence_reasons": why,
                "assumptions": list(c.meta.get("assumptions", [])) + list(d.meta.get("assumptions", [])),
                "next_best_drops": [
                    {"drop": t[0].name, "delta_win_prob": round(t[2], 4)} for t in trials[1:3]
                ],
            }
        )

    memos.sort(key=lambda m: (m["delta_win_prob"], m["delta_expected_category_wins"]), reverse=True)
    for i, m in enumerate(memos, 1):
        m["rank"] = i
    return {
        "baseline": public(base),
        "memos": memos[:max_memos],
        "not_evaluated": not_evaluated,
        "assumptions": base["assumptions"]
        + [
            "Moves ranked by change in matchup-win probability (common random numbers), "
            "then by change in expected category wins.",
            "Only this week's matchup is scored; season-long value and waiver priority are not.",
        ]
        + list(extra_assumptions),
    }


__all__ = ["recommend_moves", "SimTeam"]
