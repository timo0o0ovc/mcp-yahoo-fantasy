"""
Yahoo Fantasy Sports MCP server.

STRICTLY READ-ONLY FORK. No tool here changes anything in Yahoo: there are no lineup,
add/drop, waiver or trade tools, every tool is annotated readOnlyHint=True, and
readonly.py blocks yahoo_fantasy_api's write paths. tests/test_read_only.py enforces it.

Tools wrap yahoo_fantasy_api and return its plain dicts/lists (JSON-ready) directly.
Reads cover leagues, teams, rosters, matchups, players, stats, drafts, and transactions.
Analytics tools (NBA 9-cat H2H) add schedule counts, recent-form projections, a Monte
Carlo matchup simulator and ranked move memos. Works across NFL/NHL/NBA/MLB for the
Yahoo reads -- the sport is implied by the league key, except list_leagues.

League/team keys are optional on most tools; see client.py for the defaulting rules.
"""

import datetime as dt

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .client import client

mcp = FastMCP("yahoo")

READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
)


def read_tool():
    """The only way tools are registered in this fork: always annotated read-only."""
    return mcp.tool(annotations=READ_ONLY)


# --- League reads -----------------------------------------------------------------


@read_tool()
def list_leagues(game_code: str, year: int | None = None) -> dict:
    """List the authenticated user's league keys for a sport.

    game_code is one of nfl, nhl, nba, mlb. year filters to a season (e.g. 2024).
    Returns the game id and the league keys (e.g. "449.l.365083") to pass to other tools.
    """
    game = client.game(game_code)
    # game_codes filters to this sport; without it Yahoo returns every game's leagues.
    return {
        "game_code": game_code,
        "game_id": game.game_id(),
        "league_keys": game.league_ids(year=year, game_codes=[game_code]),
    }


@read_tool()
def league_settings(league_key: str | None = None) -> dict:
    """League settings: scoring type, roster size, current/start/end week, FAAB, etc."""
    return client.league(league_key).settings()


@read_tool()
def league_standings(league_key: str | None = None) -> list:
    """League standings, ordered first place to last, with records and games back."""
    return client.league(league_key).standings()


@read_tool()
def league_teams(league_key: str | None = None) -> dict:
    """All teams in the league, keyed by team key, with managers and metadata."""
    return client.league(league_key).teams()


@read_tool()
def league_matchups(week: int | None = None, league_key: str | None = None) -> dict:
    """Raw scoreboard/matchup data for a week (defaults to the current week)."""
    return client.league(league_key).matchups(week)


@read_tool()
def league_draft_results(league_key: str | None = None) -> list:
    """Draft results: pick, round, team key, player id (and cost for auction leagues)."""
    return client.league(league_key).draft_results()


@read_tool()
def league_transactions(
    tran_types: str = "add,drop,trade",
    count: int = 25,
    league_key: str | None = None,
) -> list:
    """Recent transactions. tran_types is a comma list of add, drop, commish, trade."""
    return client.league(league_key).transactions(tran_types, str(count))


@read_tool()
def league_stat_categories(league_key: str | None = None) -> list:
    """The league's scoring stat categories (display name + position type)."""
    return client.league(league_key).stat_categories()


@read_tool()
def league_roster_positions(league_key: str | None = None) -> dict:
    """Roster position slots and counts (e.g. C, RW, BN, IR)."""
    return client.league(league_key).positions()


@read_tool()
def current_week(league_key: str | None = None) -> dict:
    """The league's current and final week numbers."""
    league = client.league(league_key)
    return {"current_week": league.current_week(), "end_week": league.end_week()}


# --- Player reads -----------------------------------------------------------------


@read_tool()
def free_agents(position: str, league_key: str | None = None) -> list:
    """Available free agents at a position (e.g. "C", "RW", "QB", or "B"/"P" for type)."""
    return client.league(league_key).free_agents(position)


@read_tool()
def waivers(position: str | None = None, league_key: str | None = None) -> list:
    """Players currently on waivers, optionally filtered by position."""
    return client.league(league_key).waivers(position)


@read_tool()
def taken_players(league_key: str | None = None) -> list:
    """All players currently rostered by some team in the league."""
    return client.league(league_key).taken_players()


@read_tool()
def player_details(player: str, league_key: str | None = None) -> list:
    """Look up players by name (search) or by numeric player id."""
    query = int(player) if player.isdigit() else player
    return client.league(league_key).player_details(query)


@read_tool()
def player_stats(
    player_ids: list[int],
    req_type: str = "season",
    week: int | None = None,
    date: str | None = None,
    season: int | None = None,
    league_key: str | None = None,
) -> list:
    """Stats for players. req_type is one of season, average_season, lastweek, lastmonth,
    date, week. Pass week (NFL), date (YYYY-MM-DD), or season as required by req_type.
    """
    parsed_date = dt.date.fromisoformat(date) if date else None
    return client.league(league_key).player_stats(
        player_ids, req_type, date=parsed_date, week=week, season=season
    )


@read_tool()
def percent_owned(player_ids: list[int], league_key: str | None = None) -> list:
    """Ownership percentage across the Yahoo player pool for the given player ids."""
    return client.league(league_key).percent_owned(player_ids)


# --- Team reads -------------------------------------------------------------------


@read_tool()
def my_team_key(league_key: str | None = None) -> str:
    """The authenticated user's own team key in the league."""
    return client.team_key(None, league_key)


@read_tool()
def team_details(team_key: str | None = None, league_key: str | None = None) -> dict:
    """Team metadata. Defaults to the authenticated user's team."""
    return client.team(team_key, league_key).details()


@read_tool()
def team_roster(
    week: int | None = None,
    date: str | None = None,
    team_key: str | None = None,
    league_key: str | None = None,
) -> list:
    """A team's roster with each player's selected position. Defaults to your team and
    today; pass week or date (YYYY-MM-DD) for a different point in time.
    """
    parsed_date = dt.date.fromisoformat(date) if date else None
    return client.team(team_key, league_key).roster(week=week, day=parsed_date)


@read_tool()
def team_matchup_opponent(
    week: int, team_key: str | None = None, league_key: str | None = None
) -> str:
    """The opponent team key a team faces in a given week. Defaults to your team."""
    return client.team(team_key, league_key).matchup(week)


@read_tool()
def proposed_trades(team_key: str | None = None, league_key: str | None = None) -> list:
    """Pending trade proposals involving a team, with their transaction keys."""
    return client.team(team_key, league_key).proposed_trades()


# --- Analytics (NBA 9-cat H2H; read-only) ------------------------------------------

@read_tool()
def games_this_week(
    week: int | None = None,
    from_date: str | None = None,
    teams: list[str] | None = None,
    league_key: str | None = None,
) -> dict:
    """Games per NBA team in a Yahoo scoring week (official NBA schedule; regular-season
    games only). Returns totals, games remaining from from_date (default: today, US
    Eastern), the 4+ game teams, and games per day. teams filters by tricode (e.g. "OKC").
    """
    from .analytics.service import games_this_week_live

    return games_this_week_live(client, week, league_key, from_date, teams)


@read_tool()
def player_projection(
    player: str,
    as_of: str | None = None,
    yahoo_status: str | None = None,
    extra_evidence: list[dict] | None = None,
) -> dict:
    """Per-game projection for an NBA player from the last 14- and 30-day windows of the
    CURRENT season (nba_api game logs). Never uses last season. Includes a role check:
    team, minutes and injury must each have a source dated within 14 days, otherwise the
    role is labelled "role unverified". If no recent games exist, no projection is given.
    extra_evidence: optional dated facts from news/depth charts, each {"player", "what"
    ("team"|"role"|"minutes"|"injury"|"projected_minutes"), "value", "source", "date"
    (YYYY-MM-DD)}. Only items dated within 14 days count. Also accepted by sim_matchup
    and recommend_moves.
    """
    from .analytics.service import project_named, us_today

    proj, _ = project_named(player, as_of or us_today(), yahoo_status, extra_evidence)
    return proj



@read_tool()
def sim_matchup(
    week: int | None = None,
    opponent_team_key: str | None = None,
    team_key: str | None = None,
    from_date: str | None = None,
    n_sims: int = 10000,
    extra_evidence: list[dict] | None = None,
    manual_lines: dict | None = None,
    availability: dict | None = None,
    league_key: str | None = None,
) -> dict:
    """Monte Carlo (default 10,000 runs) of a 9-cat H2H week: FG%, FT%, 3PM, PTS, REB,
    AST, STL, BLK, TO (lower wins). FG%/FT% come from simulated makes and attempts.
    Uses verified rosters, the official schedule from from_date (default today, US
    Eastern), daily active-slot limits and week-to-date Yahoo totals. Returns win/tie/loss
    probability, expected category wins, per-category win rates, assumptions and sources.
    manual_lines: {player name: {per-game stats..., "source", "date"}} for players with no
    recent games (e.g. rookies); labelled as assumptions. availability: {name: 0..1}
    overrides per-game play probability (load management).
    """
    from .analytics.service import sim_matchup_live

    return sim_matchup_live(
        client, week, league_key, team_key, opponent_team_key, from_date, n_sims,
        extra_evidence, manual_lines, availability,
    )


@read_tool()
def recommend_moves(
    week: int | None = None,
    positions: list[str] | None = None,
    max_candidates: int = 12,
    candidate_names: list[str] | None = None,
    protect: list[str] | None = None,
    from_date: str | None = None,
    n_sims: int = 10000,
    extra_evidence: list[dict] | None = None,
    manual_lines: dict | None = None,
    availability: dict | None = None,
    team_key: str | None = None,
    league_key: str | None = None,
) -> dict:
    """Ranked add/drop decision memos for this week's matchup. Recommends only; it never
    makes a move. Each memo: action, change in matchup-win probability, change in expected
    category wins, per-category win rates before/after, assumptions, role/injury source
    dates for both players, and confidence (high/medium/low). Any player whose role is not
    verified within 14 days is flagged "role unverified" and the memo is low confidence.
    protect: player names never to drop. candidate_names limits the free agents tried.
    """
    from .analytics.service import DEFAULT_POSITIONS, recommend_moves_live

    return recommend_moves_live(
        client, week, league_key, team_key, from_date, tuple(positions or DEFAULT_POSITIONS),
        max_candidates, candidate_names, tuple(protect or ()), n_sims, extra_evidence,
        manual_lines, availability,
    )
