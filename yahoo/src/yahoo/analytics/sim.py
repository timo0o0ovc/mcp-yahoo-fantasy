"""
Schedule-aware Monte Carlo for a 9-category head-to-head matchup.

Per simulated player-game:
  minutes factor  f ~ Gamma(k=10) with mean 1 (shared by all of that game's stats,
                  so a big-minutes night lifts every category together)
  FGA ~ Poisson(rate * f);  3PA ~ Binomial(FGA, 3PA share)
  3PM ~ Binomial(3PA, p3);  2PM ~ Binomial(FGA - 3PA, p2)
  FTA ~ Poisson(rate * f);  FTM ~ Binomial(FTA, pFT)
  PTS = 2*2PM + 3*3PM + FTM  (so points, threes and FG% stay internally consistent)
  REB, AST, STL, BLK, TOV ~ Poisson(rate * f)
Shooting percentages are drawn once per simulation from a Beta posterior (recent sample
shrunk toward a league prior), which carries "true talent" uncertainty for small samples.

Team FG% and FT% are summed makes / summed attempts. TO is lower-is-better. Each player's
random stream is seeded by (seed, player key), so scenarios that differ by one player
share every other player's draws (common random numbers) and deltas are low-noise.
"""

import zlib
from dataclasses import dataclass, field

import numpy as np

from .categories import CATEGORIES, COUNTING_FIELD, LOWER_IS_BETTER, PCT_DECIMALS, TOTAL_FIELDS
from .roles import to_date

DEFAULT_SIMS = 10_000
MINUTES_SHAPE = 10.0
# League-average priors and their strength in pseudo-attempts.
PRIORS = {"2P": (0.545, 80.0), "3P": (0.360, 60.0), "FT": (0.780, 40.0)}
MANUAL_SAMPLE_GAMES = 10

# Availability per scheduled game by Yahoo status. Assumptions, overridable per player.
AVAILABILITY = {
    "": 0.93,  # healthy: ~7% rest / late scratches / load management
    "GTD": 0.55,
    "DTD": 0.55,
    "O": 0.0,
    "INJ": 0.0,
    "IL": 0.0,
    "IL+": 0.0,
    "NA": 0.0,
    "SUSP": 0.0,
}


def availability_from_status(status):
    return AVAILABILITY.get((status or "").upper(), AVAILABILITY[""])


@dataclass
class SimPlayer:
    key: str
    name: str
    per_game: dict
    game_dates: list
    p_play: float = AVAILABILITY[""]
    sample_games: int = MANUAL_SAMPLE_GAMES
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        self.game_dates = [to_date(d) for d in self.game_dates]

    @property
    def value(self):
        """Rough per-game value used only to order players when daily slots overflow."""
        g = self.per_game
        return (
            g.get("PTS", 0) + 1.2 * g.get("REB", 0) + 1.5 * g.get("AST", 0)
            + 3 * g.get("STL", 0) + 3 * g.get("BLK", 0) + g.get("FG3M", 0) - g.get("TOV", 0)
        ) * self.p_play


@dataclass
class SimTeam:
    name: str
    players: list
    actuals: dict = field(default_factory=dict)  # week-to-date totals (TOTAL_FIELDS)
    active_slots: int | None = None  # starters per day; None = no cap


def _beta_pct(rng, made, att, prior, n):
    mean, strength = prior
    a = mean * strength + max(made, 0.0)
    b = (1 - mean) * strength + max(att - made, 0.0)
    return rng.beta(a, b, size=(n, 1))


def draw_player(p, n, seed):
    """Stat draws for one player: dict field -> int array (n, games), plus 'plays' bool."""
    g = len(p.game_dates)
    rng = np.random.default_rng([seed, zlib.crc32(p.key.encode())])
    if g == 0:
        z = np.zeros((n, 0), dtype=np.int64)
        return {**{f: z for f in TOTAL_FIELDS}, "plays": np.zeros((n, 0), dtype=bool)}

    r = {k: float(v or 0) for k, v in p.per_game.items()}
    sg = max(int(p.sample_games), 1)
    fga, fg3a = r.get("FGA", 0), min(r.get("FG3A", 0), r.get("FGA", 0))
    fgm, fg3m = r.get("FGM", 0), min(r.get("FG3M", 0), r.get("FGM", 0))
    fta, ftm = r.get("FTA", 0), r.get("FTM", 0)

    p2 = _beta_pct(rng, (fgm - fg3m) * sg, (fga - fg3a) * sg, PRIORS["2P"], n)
    p3 = _beta_pct(rng, fg3m * sg, fg3a * sg, PRIORS["3P"], n)
    pft = _beta_pct(rng, ftm * sg, fta * sg, PRIORS["FT"], n)
    share3 = fg3a / fga if fga > 0 else 0.0

    talent = np.exp(rng.normal(0.0, 0.3 / np.sqrt(sg), size=(n, 1)))
    f = rng.gamma(MINUTES_SHAPE, 1.0 / MINUTES_SHAPE, size=(n, g)) * talent

    FGA = rng.poisson(fga * f)
    FG3A = rng.binomial(FGA, share3)
    FG3M = rng.binomial(FG3A, np.broadcast_to(p3, FG3A.shape))
    FG2M = rng.binomial(FGA - FG3A, np.broadcast_to(p2, FGA.shape))
    FTA = rng.poisson(fta * f)
    FTM = rng.binomial(FTA, np.broadcast_to(pft, FTA.shape))
    out = {
        "FGA": FGA,
        "FGM": FG2M + FG3M,
        "FG3M": FG3M,
        "FTA": FTA,
        "FTM": FTM,
        "PTS": 2 * FG2M + 3 * FG3M + FTM,
    }
    for fld in ("REB", "AST", "STL", "BLK", "TOV"):
        out[fld] = rng.poisson(r.get(fld, 0) * f)
    out["plays"] = rng.random((n, g)) < p.p_play
    return out


def team_totals(team, n, seed, cache=None):
    """Simulated weekly totals for a team: dict field -> float array (n,)."""
    cache = {} if cache is None else cache
    draws = {}
    for p in team.players:
        ck = (p.key, n, seed, tuple(p.game_dates), p.p_play)
        if ck not in cache:
            cache[ck] = draw_player(p, n, seed)
        draws[p.key] = cache[ck]

    totals = {f: np.full(n, float(team.actuals.get(f, 0.0))) for f in TOTAL_FIELDS}
    dates = sorted({d for p in team.players for d in p.game_dates})
    for d in dates:
        on = [
            (p, p.game_dates.index(d))
            for p in sorted(team.players, key=lambda x: -x.value)
            if d in p.game_dates
        ]
        plays = np.stack([draws[p.key]["plays"][:, i] for p, i in on], axis=1)
        if team.active_slots is not None and len(on) > team.active_slots:
            plays = plays & (np.cumsum(plays, axis=1) <= team.active_slots)
        for f in TOTAL_FIELDS:
            vals = np.stack([draws[p.key][f][:, i] for p, i in on], axis=1)
            totals[f] += (vals * plays).sum(axis=1)
    return totals


def category_values(t):
    out = {}
    for cat in CATEGORIES:
        if cat == "FG%":
            out[cat] = _ratio(t["FGM"], t["FGA"])
        elif cat == "FT%":
            out[cat] = _ratio(t["FTM"], t["FTA"])
        else:
            out[cat] = t[COUNTING_FIELD[cat]]
    return out


def _ratio(m, a):
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(a > 0, m / np.where(a > 0, a, 1), 0.0)
    return np.round(r, PCT_DECIMALS)


def compare(a_tot, b_tot):
    a, b = category_values(a_tot), category_values(b_tot)
    n = len(next(iter(a.values())))
    wins = np.zeros(n)
    losses = np.zeros(n)
    per_cat = {}
    for cat in CATEGORIES:
        if cat in LOWER_IS_BETTER:
            w, l = a[cat] < b[cat], a[cat] > b[cat]
        else:
            w, l = a[cat] > b[cat], a[cat] < b[cat]
        t = ~(w | l)
        wins += w
        losses += l
        per_cat[cat] = {
            "win": round(float(w.mean()), 4),
            "tie": round(float(t.mean()), 4),
            "loss": round(float(l.mean()), 4),
            "mean_a": round(float(a[cat].mean()), 3),
            "mean_b": round(float(b[cat].mean()), 3),
        }
    ties = len(CATEGORIES) - wins - losses
    p_win = float((wins > losses).mean())
    p_tie = float((wins == losses).mean())
    return {
        "win_prob": round(p_win, 4),
        "tie_prob": round(p_tie, 4),
        "loss_prob": round(1 - p_win - p_tie, 4),
        "expected_category_wins": round(float((wins + 0.5 * ties).mean()), 3),
        "categories": per_cat,
        "win_prob_std_error": round(float(np.sqrt(p_win * (1 - p_win) / n)), 4),
        "n_sims": n,
        "_cat_score": wins + 0.5 * ties,
        "_won": wins > losses,
    }


def sim_matchup(team_a, team_b, n_sims=DEFAULT_SIMS, seed=20261009, cache=None):
    """Simulate team_a vs team_b. Probabilities and category rates are from team_a's side."""
    cache = {} if cache is None else cache
    a = team_totals(team_a, n_sims, seed, cache)
    b = team_totals(team_b, n_sims, seed + 1, cache)
    res = compare(a, b)
    res["team_a"], res["team_b"] = team_a.name, team_b.name
    res["games_scheduled"] = {
        team_a.name: sum(len(p.game_dates) for p in team_a.players),
        team_b.name: sum(len(p.game_dates) for p in team_b.players),
    }
    res["assumptions"] = [
        f"{n_sims:,} simulations; per-game minutes variance Gamma(k={MINUTES_SHAPE:g}).",
        "FG%/FT% = summed makes / summed attempts, compared at 3 decimals; TO lower wins.",
        "Shooting % drawn from Beta posterior: recent sample shrunk to league priors "
        + ", ".join(f"{k} {v[0]:.3f} ({v[1]:g} att)" for k, v in PRIORS.items()) + ".",
        "Availability per game from Yahoo status: healthy 0.93, GTD/DTD 0.55, O/INJ/NA 0.",
        "Daily slot cap fills highest-value players who play; positional eligibility and "
        "late-scratch timing are ignored (slightly optimistic for both sides).",
    ]
    return res


def public(result):
    """Strip internal arrays before returning JSON."""
    return {k: v for k, v in result.items() if not k.startswith("_")}
