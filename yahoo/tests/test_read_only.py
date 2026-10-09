"""
The fork is strictly read-only. Every test here fails if a write path is exposed.

To add a tool: it must be a read, and you must add its name to EXPECTED_TOOLS below.
That forces a deliberate review of every new tool.
"""

import ast
import asyncio
import pathlib
import re

import pytest

from yahoo import readonly
from yahoo.readonly import (
    KNOWN_WRITE_TOOLS,
    TEAM_WRITE_METHODS,
    YHANDLER_WRITE_METHODS,
    ReadOnlyLeague,
    ReadOnlyTeam,
    ReadOnlyViolation,
)
from yahoo.server import mcp

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "yahoo"

EXPECTED_TOOLS = {
    # Yahoo reads
    "list_leagues", "league_settings", "league_standings", "league_teams",
    "league_matchups", "league_draft_results", "league_transactions",
    "league_stat_categories", "league_roster_positions", "current_week",
    "free_agents", "waivers", "taken_players", "player_details", "player_stats",
    "percent_owned", "my_team_key", "team_details", "team_roster",
    "team_matchup_opponent", "proposed_trades",
    # Analytics (pure computation over reads)
    "games_this_week", "player_projection", "sim_matchup", "recommend_moves",
}

WRITE_VERBS = re.compile(
    r"^(set|add|drop|claim|accept|reject|propose|edit|change|update|delete|remove|"
    r"post|put|send|submit|trade|move|swap|start|bench|activate|waive)_"
)


@pytest.fixture(scope="module")
def tools():
    return asyncio.run(mcp.list_tools())


def test_no_known_write_tool_is_registered(tools):
    exposed = {t.name for t in tools} & KNOWN_WRITE_TOOLS
    assert not exposed, f"write tools exposed: {sorted(exposed)}"


def test_no_tool_name_looks_like_a_write(tools):
    bad = [t.name for t in tools if WRITE_VERBS.match(t.name)]
    assert not bad, f"tool names that read as writes: {bad}"


def test_tool_set_is_exactly_the_reviewed_allowlist(tools):
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOLS, (
        f"unreviewed tools: {sorted(names - EXPECTED_TOOLS)}; "
        f"missing: {sorted(EXPECTED_TOOLS - names)}"
    )


def test_every_tool_is_annotated_read_only(tools):
    for t in tools:
        assert t.annotations is not None, t.name
        assert t.annotations.readOnlyHint is True, t.name
        assert t.annotations.destructiveHint is False, t.name


def test_source_never_calls_a_yahoo_write_method():
    """AST scan: no attribute call to a Team/YHandler write method anywhere in the package."""
    forbidden = TEAM_WRITE_METHODS | YHANDLER_WRITE_METHODS
    hits = []
    for path in SRC.rglob("*.py"):
        if path.name == "readonly.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in forbidden:
                    hits.append(f"{path.name}:{node.lineno} .{node.func.attr}()")
    assert not hits, hits


def test_server_never_registers_tools_without_read_only_wrapper():
    tree = ast.parse((SRC / "server.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                target = dec.func if isinstance(dec, ast.Call) else dec
                if isinstance(target, ast.Attribute) and target.attr == "tool":
                    assert node.name == "read_tool", f"{node.name} uses mcp.tool directly"


class _FakeTeam:
    def roster(self):
        return ["ok"]

    def __getattr__(self, name):
        return lambda *a, **k: f"WROTE {name}"


@pytest.mark.parametrize("method", sorted(TEAM_WRITE_METHODS))
def test_team_proxy_blocks_every_write(method):
    team = ReadOnlyTeam(_FakeTeam())
    with pytest.raises(ReadOnlyViolation):
        getattr(team, method)(1)
    assert team.roster() == ["ok"]


def test_league_proxy_returns_read_only_teams():
    class _FakeLeague:
        def to_team(self, key):
            return _FakeTeam()

    team = ReadOnlyLeague(_FakeLeague()).to_team("x")
    with pytest.raises(ReadOnlyViolation):
        team.add_player(1)


@pytest.mark.parametrize("method", sorted(YHANDLER_WRITE_METHODS))
def test_yhandler_http_writes_are_disabled(method):
    import yahoo.client  # noqa: F401  (import applies the lock)
    from yahoo_fantasy_api.yhandler import YHandler

    assert getattr(YHandler, "_read_only_locked", False)
    with pytest.raises(ReadOnlyViolation):
        getattr(YHandler, method)(object(), "uri", "data")


def test_upstream_team_write_methods_are_all_covered():
    """If yahoo_fantasy_api grows a new mutating Team method, this flags it."""
    import yahoo_fantasy_api as yfa

    reads = {"details", "matchup", "proposed_trades", "roster", "inject_yhandler"}
    public = {m for m in dir(yfa.Team) if not m.startswith("_")}
    assert public - reads <= TEAM_WRITE_METHODS, sorted(public - reads - TEAM_WRITE_METHODS)


def test_client_uses_proxies():
    src = (SRC / "client.py").read_text()
    assert "ReadOnlyTeam(" in src and "ReadOnlyLeague(" in src and "lock_yhandler()" in src
    assert readonly.ReadOnlyViolation is ReadOnlyViolation
