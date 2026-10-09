"""
Live NBA data via nba_api (stats.nba.com). Everything returned is stamped with the
date it was fetched, so downstream role checks can enforce the 14-day freshness rule.

stats.nba.com throttles aggressive clients; calls are spaced by REQUEST_GAP seconds.
"""

import datetime as dt
import re
import time
import unicodedata
from functools import lru_cache

REQUEST_GAP = 0.7
TIMEOUT = 30
_last_call = [0.0]


def _pace():
    wait = REQUEST_GAP - (time.monotonic() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.monotonic()


def _us(d):
    return d.strftime("%m/%d/%Y")


def fetch_game_logs(player_id, season, as_of, days=30):
    """This season's regular-season and preseason logs dated within `days` of as_of."""
    from nba_api.stats.endpoints import playergamelogs

    as_of = dt.date.fromisoformat(str(as_of)[:10])
    rows = []
    for season_type in ("Regular Season", "Pre Season"):
        _pace()
        resp = playergamelogs.PlayerGameLogs(
            player_id_nullable=str(player_id),
            season_nullable=season,
            season_type_nullable=season_type,
            date_from_nullable=_us(as_of - dt.timedelta(days=days)),
            date_to_nullable=_us(as_of),
            timeout=TIMEOUT,
        )
        for r in resp.get_normalized_dict()["PlayerGameLogs"]:
            r["SEASON_TYPE"] = season_type
            rows.append(r)
    return rows


@lru_cache(maxsize=4)
def _schedule_cached(season, day):
    from nba_api.stats.endpoints import scheduleleaguev2

    _pace()
    df = scheduleleaguev2.ScheduleLeagueV2(season=season, timeout=TIMEOUT).get_data_frames()[0]
    cols = ["gameId", "gameDate", "gameDateEst", "homeTeam_teamTricode", "awayTeam_teamTricode"]
    df = df[[c for c in cols if c in df.columns]]
    return [{k: (str(v) if v is not None else None) for k, v in r.items()} for r in df.to_dict("records")]


def fetch_schedule(season):
    """Full-season schedule rows; cached per process per calendar day."""
    today = dt.date.today().isoformat()
    return _schedule_cached(season, today), today


@lru_cache(maxsize=4)
def _directory_cached(season, day):
    from nba_api.stats.endpoints import commonallplayers

    _pace()
    d = commonallplayers.CommonAllPlayers(
        is_only_current_season=1, season=season, timeout=TIMEOUT
    ).get_normalized_dict()["CommonAllPlayers"]
    return [
        {
            "id": r["PERSON_ID"],
            "name": r["DISPLAY_FIRST_LAST"],
            "team": r.get("TEAM_ABBREVIATION") or None,
            "roster_status": r.get("ROSTERSTATUS"),
        }
        for r in d
    ]


def player_directory(season):
    """Current-season players with their current NBA team, fetched today."""
    today = dt.date.today().isoformat()
    return _directory_cached(season, today), today


_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def normalize_name(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z ]", " ", s.replace("-", " "))
    s = _SUFFIX.sub(" ", s)
    return " ".join(s.split())


def resolve_player(name, directory):
    """Match a Yahoo display name to one directory entry, or None if missing/ambiguous."""
    target = normalize_name(name)
    hits = [p for p in directory if normalize_name(p["name"]) == target]
    return hits[0] if len(hits) == 1 else None
