"""
Glue between Yahoo (rosters, week dates, live scores) and NBA data (logs, schedule,
current teams). The MCP tools in server.py call these; everything here only reads.

Dates: NBA game days are US dates, so "today" defaults to the current date in
America/New_York, not the caller's local time.
"""

import datetime as dt
from zoneinfo import ZoneInfo

from . import nba_data
from .projection import current_season, manual_projection, player_projection
from .recommend import recommend_moves
from .roles import Evidence, to_date
from .schedule import games_this_week, team_game_dates
from .sim import DEFAULT_SIMS, SimPlayer, SimTeam, availability_from_status, public, sim_matchup
from .yahoo_parse import week_totals

INACTIVE_SLOTS = {"BN", "IL", "IL+", "IR", "NA"}
INJURED_SLOTS = {"IL", "IL+", "IR"}
DEFAULT_POSITIONS = ("PG", "SG", "SF", "PF", "C")


def us_today():
    return dt.datetime.now(ZoneInfo("America/New_York")).date()


def week_dates(league, week):
    start, end = league.week_date_range(int(week))
    return to_date(start), to_date(end)


def active_slots(league):
    total = 0
    for pos, info in league.positions().items():
        if pos not in INACTIVE_SLOTS:
            total += int(info.get("count", 0)) if isinstance(info, dict) else int(info)
    return total or None


def _evidence_for(name, extra):
    key = nba_data.normalize_name(name)
    out = []
    for e in extra or ():
        if nba_data.normalize_name(e.get("player", "")) == key:
            out.append(Evidence(e["what"], e["value"], e["source"], e["date"]))
    return out


def project_named(name, as_of, yahoo_status=None, extra_evidence=(), manual_lines=None,
                  directory=None, directory_date=None):
    """Projection dict for one player name, with every source dated."""
    as_of = to_date(as_of)
    season = current_season(as_of)
    if directory is None:
        directory, directory_date = nba_data.player_directory(season)
    hit = nba_data.resolve_player(name, directory)
    evidence = _evidence_for(name, extra_evidence)
    if yahoo_status is not None:
        evidence.append(Evidence("injury", yahoo_status or "healthy", "Yahoo player status", as_of))
    if hit and hit.get("team"):
        evidence.append(Evidence("team", hit["team"], "stats.nba.com commonallplayers", directory_date))

    proj_minutes = None
    fresh_min = [e for e in evidence if e.what == "projected_minutes" and e.is_fresh(as_of)]
    if fresh_min:
        latest = max(fresh_min, key=lambda e: e.date)
        proj_minutes = float(latest.value)
        evidence.append(Evidence("minutes", proj_minutes, latest.source, latest.date))

    if not hit:
        line = (manual_lines or {}).get(name)
        if line:
            p = manual_projection(name, line, line.get("source", "caller"), line.get("date", as_of), as_of, evidence)
            p.assumptions.append("Name not matched to a current NBA player id.")
            return p.to_dict(), None
        return {
            "name": name, "status": "unresolved", "per_game": None,
            "role": {"label": "role unverified", "unverified_reasons": ["name not matched to a current-season NBA player"], "sources": []},
            "assumptions": ["Could not match Yahoo name to stats.nba.com; not projected."],
        }, None

    rows = nba_data.fetch_game_logs(hit["id"], season, as_of)
    proj = player_projection(rows, as_of, hit["id"], name, evidence=evidence, projected_minutes=proj_minutes)
    if proj.status != "ok" and manual_lines and name in manual_lines:
        line = manual_lines[name]
        proj = manual_projection(name, line, line.get("source", "caller"), line.get("date", as_of), as_of, evidence, hit["id"])
    return proj.to_dict(), hit


def _sim_player(yp, ctx, label):
    name = yp["name"]
    status = yp.get("status", "")
    proj, hit = project_named(
        name, ctx["as_of"], status, ctx["evidence"], ctx["manual"], ctx["directory"], ctx["directory_date"]
    )
    team = (proj.get("role") or {}).get("team") or (hit or {}).get("team")
    dates = ctx["dates"].get(team, []) if team else []
    avail = ctx["availability"].get(name, availability_from_status(status))
    meta = {
        "role": proj.get("role"),
        "games_used": proj.get("games_used", 0),
        "preseason_used": proj.get("preseason_used", False),
        "assumptions": [f"{name}: {a}" for a in proj.get("assumptions", [])],
        "reason": "; ".join(proj.get("assumptions", [])) or None,
        "yahoo_player_id": yp.get("player_id"),
        "side": label,
    }
    sample = proj.get("games_used") or 10
    return SimPlayer(f"{label}:{name}", name, proj.get("per_game"), dates, avail, sample, meta), proj


def _context(league, week, from_date, extra_evidence, manual_lines, availability):
    as_of = to_date(from_date) if from_date else us_today()
    start, end = week_dates(league, week)
    season = current_season(start)
    sched, sched_date = nba_data.fetch_schedule(season)
    directory, directory_date = nba_data.player_directory(season)
    lo = max(as_of, start)
    return {
        "as_of": min(as_of, end),
        "start": start,
        "end": end,
        "from": lo,
        "dates": team_game_dates(sched, start, end, lo),
        "schedule": sched,
        "schedule_date": sched_date,
        "directory": directory,
        "directory_date": directory_date,
        "evidence": extra_evidence or [],
        "manual": manual_lines or {},
        "availability": availability or {},
    }


def build_team(name, roster, ctx, label, actuals, slots):
    players, notes = [], []
    for yp in roster:
        if yp.get("selected_position") in INJURED_SLOTS:
            notes.append(f"{yp['name']} is in an IL slot; excluded (stats would not count).")
            continue
        sp, proj = _sim_player(yp, ctx, label)
        if not sp.per_game:
            notes.append(f"{yp['name']}: {proj.get('role', {}).get('label', 'role unverified')} and no usable projection; excluded from simulation.")
            continue
        players.append(sp)
    return SimTeam(name, players, actuals or {}, slots), notes


def _actuals(league, week, team_key, ctx):
    if ctx["from"] <= ctx["start"]:
        return {}, None
    tot = week_totals(league.matchups(int(week)), team_key)
    return (tot or {}), ("Yahoo scoreboard week-to-date totals" if tot else "week-to-date totals not found")


def sim_matchup_live(client, week=None, league_key=None, team_key=None, opponent_key=None,
                     from_date=None, n_sims=DEFAULT_SIMS, extra_evidence=None, manual_lines=None,
                     availability=None, seed=20261009):
    league = client.league(league_key)
    week = week or league.current_week()
    ctx = _context(league, week, from_date, extra_evidence, manual_lines, availability)
    my_key = client.team_key(team_key, league_key)
    opp_key = opponent_key or client.team(my_key, league_key).matchup(int(week))
    slots = active_slots(league)
    day = ctx["from"]

    teams, notes, act_src = [], [], []
    for key, label in ((my_key, "A"), (opp_key, "B")):
        roster = client.team(key, league_key).roster(day=day)
        actual, src = _actuals(league, week, key, ctx)
        if src:
            act_src.append(f"{key}: {src}")
        t, n = build_team(key, roster, ctx, label, actual, slots)
        teams.append(t)
        notes += n
    res = public(sim_matchup(teams[0], teams[1], n_sims, seed))
    res["week"] = int(week)
    res["week_dates"] = [ctx["start"].isoformat(), ctx["end"].isoformat()]
    res["simulated_from"] = ctx["from"].isoformat()
    res["active_slots_per_day"] = slots
    res["roster_notes"] = notes
    res["week_to_date_source"] = act_src or ["week not started; no actuals"]
    res["sources"] = {
        "schedule": f"stats.nba.com scheduleleaguev2, fetched {ctx['schedule_date']}",
        "teams": f"stats.nba.com commonallplayers, fetched {ctx['directory_date']}",
        "logs": "stats.nba.com playergamelogs (last 14/30 days, current season only)",
        "rosters_and_status": f"Yahoo Fantasy API, fetched {us_today().isoformat()}",
    }
    res["players"] = {t.name: [_player_summary(p) for p in t.players] for t in teams}
    return res


def _player_summary(p):
    role = p.meta.get("role") or {}
    return {
        "name": p.name,
        "role_status": role.get("label"),
        "team": role.get("team"),
        "remaining_games": len(p.game_dates),
        "availability_per_game": p.p_play,
        "games_in_projection": p.meta.get("games_used"),
        "preseason_used": p.meta.get("preseason_used"),
    }


def recommend_moves_live(client, week=None, league_key=None, team_key=None, from_date=None,
                         positions=DEFAULT_POSITIONS, max_candidates=12, candidate_names=None,
                         protect=(), n_sims=DEFAULT_SIMS, extra_evidence=None, manual_lines=None,
                         availability=None, seed=20261009):
    league = client.league(league_key)
    week = week or league.current_week()
    ctx = _context(league, week, from_date, extra_evidence, manual_lines, availability)
    my_key = client.team_key(team_key, league_key)
    opp_key = client.team(my_key, league_key).matchup(int(week))
    slots = active_slots(league)
    day = ctx["from"]

    my_roster = client.team(my_key, league_key).roster(day=day)
    opp_roster = client.team(opp_key, league_key).roster(day=day)
    my_act, _ = _actuals(league, week, my_key, ctx)
    opp_act, _ = _actuals(league, week, opp_key, ctx)
    my_team, n1 = build_team(my_key, my_roster, ctx, "A", my_act, slots)
    opp_team, n2 = build_team(opp_key, opp_roster, ctx, "B", opp_act, slots)

    pool = {}
    for pos in positions:
        for fa in league.free_agents(pos):
            pool.setdefault(fa["player_id"], fa)
    fas = sorted(pool.values(), key=lambda f: -float(f.get("percent_owned") or 0))
    if candidate_names:
        want = {nba_data.normalize_name(n) for n in candidate_names}
        fas = [f for f in fas if nba_data.normalize_name(f["name"]) in want]
    fas = fas[: int(max_candidates)]

    cands = []
    for fa in fas:
        sp, _ = _sim_player(fa, ctx, "A")
        cands.append(sp)
    protect_keys = {f"A:{n}" for n in protect}
    out = recommend_moves(
        my_team, opp_team, cands, n_sims, seed, protect_keys,
        extra_assumptions=n1 + n2 + [
            f"Candidates: top {len(fas)} free agents by Yahoo % owned at {', '.join(positions)}; waiver-wire players not included.",
        ],
    )
    out["week"] = int(week)
    out["simulated_from"] = ctx["from"].isoformat()
    out["sources"] = {
        "schedule": f"stats.nba.com scheduleleaguev2, fetched {ctx['schedule_date']}",
        "teams": f"stats.nba.com commonallplayers, fetched {ctx['directory_date']}",
        "rosters_free_agents_status": f"Yahoo Fantasy API, fetched {us_today().isoformat()}",
    }
    return out


def games_this_week_live(client, week=None, league_key=None, from_date=None, teams=None):
    league = client.league(league_key)
    week = week or league.current_week()
    start, end = week_dates(league, week)
    sched, fetched = nba_data.fetch_schedule(current_season(start))
    out = games_this_week(sched, start, end, from_date or us_today(), teams, fetched)
    out["week"] = int(week)
    return out


__all__ = [
    "games_this_week_live", "project_named", "recommend_moves_live", "sim_matchup_live", "us_today",
]
