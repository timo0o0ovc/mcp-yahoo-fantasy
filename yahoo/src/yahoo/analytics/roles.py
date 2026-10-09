"""
Role / health verification.

A player's role is "verified" only when every one of team, role/minutes and injury
status is backed by a source dated within FRESHNESS_DAYS of `as_of`. Anything older --
including last season's role -- does not count. If any piece is missing or stale, the
label is exactly ROLE_UNVERIFIED and the reasons say which piece failed.
"""

import datetime as dt
from dataclasses import asdict, dataclass, field

FRESHNESS_DAYS = 14
ROLE_UNVERIFIED = "role unverified"
ROLE_VERIFIED = "verified"


def to_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


@dataclass
class Evidence:
    """One dated fact about a player: what, value, where it came from, and when."""

    what: str  # "team" | "role" | "minutes" | "injury"
    value: object
    source: str
    date: dt.date | str

    def __post_init__(self):
        self.date = to_date(self.date)

    def age_days(self, as_of):
        return (to_date(as_of) - self.date).days

    def is_fresh(self, as_of):
        age = self.age_days(as_of)
        return 0 <= age <= FRESHNESS_DAYS


@dataclass
class RoleCheck:
    label: str
    team: str | None
    minutes_14d: float | None
    injury_status: str | None
    sources: list = field(default_factory=list)
    unverified_reasons: list = field(default_factory=list)
    preseason_only: bool = False

    @property
    def verified(self):
        return self.label == ROLE_VERIFIED

    def to_dict(self):
        d = asdict(self)
        d["verified"] = self.verified
        return d


def check_role(as_of, recent_rows=(), evidence=()):
    """
    Decide whether a player's role is verified as of `as_of`.

    recent_rows: this season's game-log rows (dicts with GAME_DATE, MIN, TEAM_ABBREVIATION,
                 SEASON_TYPE). Rows dated within 14 days count as role/minutes evidence.
    evidence:    Evidence items from other sources (Yahoo status fetched today, NBA player
                 info fetched today, a dated news report, etc.).
    """
    as_of = to_date(as_of)
    fresh = [e for e in evidence if e.is_fresh(as_of)]
    sources = [
        {
            "what": e.what,
            "value": e.value,
            "source": e.source,
            "date": e.date.isoformat(),
            "age_days": e.age_days(as_of),
            "fresh": e.is_fresh(as_of),
        }
        for e in evidence
    ]
    reasons = []

    window = [
        r
        for r in recent_rows
        if 0 <= (as_of - to_date(r["GAME_DATE"])).days <= FRESHNESS_DAYS
    ]
    regular = [r for r in window if r.get("SEASON_TYPE", "Regular Season") == "Regular Season"]
    use = regular or window
    preseason_only = bool(window) and not regular

    minutes = None
    if use:
        minutes = round(sum(float(r["MIN"] or 0) for r in use) / len(use), 1)
        last = max(to_date(r["GAME_DATE"]) for r in use)
        sources.append(
            {
                "what": "minutes",
                "value": minutes,
                "source": "stats.nba.com player game logs"
                + (" (preseason only)" if preseason_only else ""),
                "date": last.isoformat(),
                "age_days": (as_of - last).days,
                "fresh": True,
            }
        )

    def latest(what):
        items = [e for e in fresh if e.what == what]
        return max(items, key=lambda e: e.date) if items else None

    team_ev = latest("team")
    team = team_ev.value if team_ev else None
    if team is None and use:
        last_row = max(use, key=lambda r: to_date(r["GAME_DATE"]))
        team = last_row.get("TEAM_ABBREVIATION")
    if team is None:
        reasons.append(f"no team source within {FRESHNESS_DAYS} days")

    role_ev = latest("role") or latest("minutes")
    if not use and role_ev is None:
        reasons.append(f"no games or dated role/minutes report within {FRESHNESS_DAYS} days")
    if minutes is None and role_ev is not None and role_ev.what == "minutes":
        minutes = float(role_ev.value)

    inj_ev = latest("injury")
    injury = inj_ev.value if inj_ev else None
    if inj_ev is None:
        reasons.append(f"no injury-status source within {FRESHNESS_DAYS} days")

    label = ROLE_VERIFIED if not reasons else ROLE_UNVERIFIED
    return RoleCheck(
        label=label,
        team=team,
        minutes_14d=minutes,
        injury_status=injury,
        sources=sources,
        unverified_reasons=reasons,
        preseason_only=preseason_only,
    )
