"""
Per-game player projections from recent game logs only.

Projections use the last 14- and 30-day windows of the *current* season. Rows from any
other season, or older than 30 days, are discarded before anything is computed -- so a
player with no recent games gets no projection rather than last season's line.
"""

from dataclasses import dataclass, field

from .roles import Evidence, RoleCheck, check_role, to_date

RATE_FIELDS = (
    "MIN", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "PTS", "REB", "AST", "STL", "BLK", "TOV"
)
DEFAULT_WINDOWS = (14, 30)
DEFAULT_WEIGHTS = {14: 0.6, 30: 0.4}
MIN_REGULAR_GAMES = 3


def current_season(as_of):
    """NBA season string for a date, e.g. 2026-10-09 -> '2026-27'."""
    d = to_date(as_of)
    start = d.year if d.month >= 8 else d.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


@dataclass
class PlayerProjection:
    player_id: int | None
    name: str
    as_of: str
    season: str
    status: str  # "ok" | "no_recent_games"
    per_game: dict | None
    windows: dict
    games_used: int
    last_game_date: str | None
    preseason_used: bool
    role: RoleCheck
    assumptions: list = field(default_factory=list)

    def to_dict(self):
        return {
            "player_id": self.player_id,
            "name": self.name,
            "as_of": self.as_of,
            "season": self.season,
            "status": self.status,
            "per_game": self.per_game,
            "windows": self.windows,
            "games_used": self.games_used,
            "last_game_date": self.last_game_date,
            "preseason_used": self.preseason_used,
            "role": self.role.to_dict(),
            "assumptions": self.assumptions,
        }


def _mean(rows):
    n = len(rows)
    return {f: sum(float(r.get(f) or 0) for r in rows) / n for f in RATE_FIELDS}


def player_projection(
    rows,
    as_of,
    player_id=None,
    name="",
    windows=DEFAULT_WINDOWS,
    weights=None,
    evidence=(),
    projected_minutes=None,
):
    """
    Build a projection from game-log rows.

    rows: dicts shaped like nba_api PlayerGameLogs rows, each with SEASON_YEAR and a
          SEASON_TYPE of "Regular Season" or "Pre Season".
    projected_minutes: optional minutes from a dated (<=14 day) source. When given,
          per-minute rates are rescaled to this many minutes.
    """
    as_of_d = to_date(as_of)
    season = current_season(as_of_d)
    weights = weights or DEFAULT_WEIGHTS
    longest = max(windows)
    assumptions = []

    in_season = [r for r in rows if r.get("SEASON_YEAR") == season]
    dropped = len(rows) - len(in_season)
    if dropped:
        assumptions.append(f"Ignored {dropped} game(s) from other seasons (never last season's role).")

    def age(r):
        return (as_of_d - to_date(r["GAME_DATE"])).days

    recent = [r for r in in_season if 0 <= age(r) <= longest]
    regular = [r for r in recent if r.get("SEASON_TYPE", "Regular Season") == "Regular Season"]
    preseason_used = len(regular) < MIN_REGULAR_GAMES and len(recent) > len(regular)
    pool = recent if preseason_used else regular
    if preseason_used:
        assumptions.append(
            f"Fewer than {MIN_REGULAR_GAMES} regular-season games in {longest} days; "
            "preseason games included. Preseason minutes and usage are unreliable."
        )

    win_stats = {}
    for w in windows:
        wr = [r for r in pool if age(r) <= w]
        win_stats[w] = {
            "days": w,
            "games": len(wr),
            "per_game": {k: round(v, 3) for k, v in _mean(wr).items()} if wr else None,
            "first_game": min(r["GAME_DATE"][:10] for r in wr) if wr else None,
            "last_game": max(r["GAME_DATE"][:10] for r in wr) if wr else None,
        }

    role = check_role(as_of_d, in_season, evidence)

    if not pool:
        assumptions.append(f"No current-season games in the last {longest} days; no projection.")
        return PlayerProjection(
            player_id, name, as_of_d.isoformat(), season, "no_recent_games", None,
            win_stats, 0, None, False, role, assumptions,
        )

    usable = {w: s for w, s in win_stats.items() if s["games"]}
    total_w = sum(weights.get(w, 0) for w in usable)
    if total_w == 0:
        usable = {longest: win_stats[longest]}
        total_w = 1.0
        blend = {longest: 1.0}
    else:
        blend = {w: weights.get(w, 0) / total_w for w in usable}
    per_game = {
        f: sum(blend[w] * _mean([r for r in pool if age(r) <= w])[f] for w in blend)
        for f in RATE_FIELDS
    }
    assumptions.append(
        "Blend: " + ", ".join(f"{w}-day x{blend[w]:.2f} ({usable[w]['games']} g)" for w in blend)
        + ". Rates are per game played."
    )

    if projected_minutes is not None and per_game["MIN"] > 0:
        scale = float(projected_minutes) / per_game["MIN"]
        per_game = {f: (v * scale if f != "MIN" else float(projected_minutes)) for f, v in per_game.items()}
        assumptions.append(
            f"Rescaled per-minute rates to {projected_minutes} projected minutes (dated source)."
        )

    return PlayerProjection(
        player_id,
        name,
        as_of_d.isoformat(),
        season,
        "ok",
        {k: round(v, 3) for k, v in per_game.items()},
        win_stats,
        len(pool),
        max(r["GAME_DATE"][:10] for r in pool),
        preseason_used,
        role,
        assumptions,
    )


def manual_projection(name, per_game, source, source_date, as_of, evidence=(), player_id=None):
    """
    A caller-supplied line (e.g. a rookie with no NBA games yet). It is labelled as an
    assumption and carries its own source date; it does not bypass role verification.
    """
    as_of_d = to_date(as_of)
    full = {f: float(per_game.get(f, 0.0)) for f in RATE_FIELDS}
    role = check_role(as_of_d, (), evidence)
    return PlayerProjection(
        player_id, name, as_of_d.isoformat(), current_season(as_of_d), "ok",
        full, {}, 0, None, False, role,
        [f"Manual line from {source} dated {to_date(source_date).isoformat()} (assumption, not observed)."],
    )


__all__ = ["Evidence", "PlayerProjection", "current_season", "manual_projection", "player_projection"]
