"""
Read-only enforcement for this fork.

Three layers, so no single mistake can make the server write to Yahoo:

1. server.py registers no write tools (enforced by tests/test_read_only.py).
2. `ReadOnlyTeam` / `ReadOnlyLeague` proxies refuse every known mutating method on the
   yahoo_fantasy_api objects the tools receive.
3. `lock_yhandler()` replaces the HTTP write paths on yahoo_fantasy_api's YHandler
   (put/post and their helpers) with functions that raise, process-wide.

If you add a tool, it must be a read. If upstream adds a new write method, add it to
TEAM_WRITE_METHODS / LEAGUE_WRITE_METHODS / YHANDLER_WRITE_METHODS.
"""

TEAM_WRITE_METHODS = frozenset(
    {
        "accept_trade",
        "add_and_drop_players",
        "add_player",
        "change_positions",
        "claim_and_drop_players",
        "claim_player",
        "drop_player",
        "propose_trade",
        "reject_trade",
    }
)

LEAGUE_WRITE_METHODS = frozenset()  # yahoo_fantasy_api.League has no writes today.

YHANDLER_WRITE_METHODS = frozenset(
    {"put", "post", "put_roster", "put_transaction", "post_transactions"}
)

# Every tool name an upstream release has exposed that mutates league state. The test
# suite fails if any of these is ever registered again.
KNOWN_WRITE_TOOLS = frozenset(
    {
        "set_lineup",
        "add_player",
        "drop_player",
        "add_and_drop_players",
        "claim_player",
        "claim_and_drop_players",
        "accept_trade",
        "reject_trade",
        "propose_trade",
    }
)


class ReadOnlyViolation(PermissionError):
    """Raised when anything tries to write to Yahoo through this server."""


def _refuse(name):
    def _blocked(*_args, **_kwargs):
        raise ReadOnlyViolation(
            f"'{name}' is a Yahoo write and this server is strictly read-only."
        )

    _blocked.__name__ = name
    return _blocked


class _ReadOnlyProxy:
    _blocked: frozenset = frozenset()

    def __init__(self, wrapped):
        object.__setattr__(self, "_wrapped", wrapped)

    def __getattr__(self, name):
        if name in self._blocked:
            return _refuse(name)
        return getattr(self._wrapped, name)

    def __setattr__(self, name, value):
        raise ReadOnlyViolation("Read-only proxy attributes cannot be set.")


class ReadOnlyTeam(_ReadOnlyProxy):
    _blocked = TEAM_WRITE_METHODS


class ReadOnlyLeague(_ReadOnlyProxy):
    _blocked = LEAGUE_WRITE_METHODS

    def to_team(self, team_key):
        return ReadOnlyTeam(self._wrapped.to_team(team_key))


def lock_yhandler():
    """Make yahoo_fantasy_api's HTTP write paths raise. Idempotent."""
    from yahoo_fantasy_api import yhandler

    for name in YHANDLER_WRITE_METHODS:
        if hasattr(yhandler.YHandler, name):
            setattr(yhandler.YHandler, name, _refuse(f"YHandler.{name}"))
    yhandler.YHandler._read_only_locked = True
