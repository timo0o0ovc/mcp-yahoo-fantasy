# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A single MCP (Model Context Protocol) server, in [`yahoo/`](yahoo/), that wraps the Yahoo
Fantasy Sports API for STRICTLY READ-ONLY access, NBA-only (Yahoo game code `nba`), plus an NBA 9-cat
H2H `analytics/` package. It is a `uv`-managed
Python 3.12 package. (The repo previously held an NHL server too; that has been removed and
the project is now Yahoo-only.)

## Commands

Run from the repo root unless noted.

- Install deps: `./scripts/setup.sh` (wraps `cd yahoo && uv sync`).
- One-time Yahoo login: `cd yahoo && uv run yahoo-login --client-id <id> --client-secret <secret>`
  (out-of-band OAuth: open the printed URL, approve, paste back the verifier code). Writes
  credentials to `.env` in the working directory. Flags fall back to env vars / `.env` / prompt.
- Run the server: `cd yahoo && uv run yahoo` (stdio transport).
- Debug with the MCP Inspector: `./scripts/debug.sh`.
- Add a dependency: `cd yahoo && uv add <pkg>` (keeps `pyproject.toml` + `uv.lock` in sync).
- Sanity-check tool registration without credentials:
  `cd yahoo && uv run python -c "import asyncio; from yahoo.server import mcp; print(len(asyncio.run(mcp.list_tools())))"`

Environment note: `uv lock`/`uv sync` need network; in a sandboxed shell run them with the
sandbox disabled. Redirecting command output to `/tmp` also fails under the sandbox.

Tests: `cd yahoo && uv run pytest` (fixtures/stubs, no credentials or network).
`tests/test_read_only.py` is the read-only gate: never weaken it. A new tool must be a read,
registered with `@read_tool()`, and added to its `EXPECTED_TOOLS` allowlist. Live behavior
still needs real Yahoo credentials and network access to stats.nba.com.

## Architecture

Built on `FastMCP` (`mcp.server.fastmcp`). Modules under `src/yahoo/`, each a deep
layer hiding one concern:

- `readonly.py` — read-only enforcement: `ReadOnlyTeam`/`ReadOnlyLeague` proxies, the
  `lock_yhandler()` patch that disables Yahoo PUT/POST, and the known write-tool names.
- `analytics/` — pure functions (`sim_matchup`, `player_projection`, `games_this_week`,
  `recommend_moves`, `roles.check_role`) plus `nba_data.py` (nba_api fetchers) and
  `service.py` (wires Yahoo + NBA data for the tools). Projections use only the current
  season's last 14/30 days; roles need sources dated within 14 days or are labelled
  "role unverified". Never add a fallback to last season's data.
- `server.py` — the `FastMCP("yahoo")` instance and 25 `@read_tool()` functions. Tools are
  intentionally thin: resolve args, call one `client` method, return the result. They return
  `yahoo_fantasy_api`'s plain dicts/lists, which FastMCP serializes to JSON for the model.
  Each tool's docstring IS its description shown to the model, so keep them accurate.
- `client.py` — `YahooClient`, the single seam over `yahoo_fantasy_api`. It owns the OAuth
  session (lazy), caches `Game`/`League` objects, and resolves defaults: an omitted
  `league_key` falls back to `$YAHOO_LEAGUE_KEY`; an omitted `team_key` falls back to the
  authenticated user's own team (`League.team_key()`). A module-level `client` singleton is
  shared by all tools.
- `auth.py` — the OAuth2 bridge plus `.env` helpers. `yahoo_fantasy_api` reads credentials
  via `yahoo_oauth`'s `oauth2.json`. `auth.session()` calls `load_env_file()` (loads `.env`
  into the environment without clobbering real vars), then bridges `$YAHOO_CONSUMER_KEY/
  SECRET` (+ token vars) into a `oauth2.json` and returns a token-refreshed `OAuth2`.
  Credential source priority: existing `oauth2.json` -> `.env`/env vars. The bridged file is
  written to `~/.config/yahoo-fantasy-mcp/oauth2.json` (override path with `$YAHOO_OAUTH_FILE`
  or dir with `$YAHOO_MCP_CONFIG_DIR`); `.env` defaults to `./.env` (override `$YAHOO_ENV_FILE`).
- `login.py` — the `yahoo-login` CLI (a `[project.scripts]` entry point). Runs `yahoo_oauth`'s
  out-of-band OAuth flow (`OAuth2(..., browser_callback=False, store_file=False)`), then
  `write_env()`s the resulting client id/secret + access/refresh tokens to `.env` and deletes
  any stale `oauth2.json` so the server re-bridges from the fresh `.env`.

### Time frames: week vs. date

`team_roster` and `player_stats` accept either a `week` (int) or a `date`
(`YYYY-MM-DD`) — never assume one. NBA is a daily sport, so prefer `date`.

### Key design decisions (and why)

- **Read-only fork**: all write tools were removed from upstream. Do not re-add them.
- **Library choice**: `yahoo_fantasy_api` returns JSON-ready dicts — ideal for MCP output. Auth (login + refresh) goes through `yahoo_oauth` directly. The repo used to
  depend on `yahoofantasy` for login, but its `login` CLI calls `ssl.wrap_socket`, removed
  in Python 3.12, so it crashes — `yahoo-login` replaces it and that dependency is dropped.
- **Lazy auth**: the OAuth session is built on first tool call, not at import, so the server
  starts (and lists tools) without credentials. Don't move auth into module import.

### Yahoo key formats

- League key: `449.l.365083` (leading number is the game/season id).
- Team key: `449.l.365083.t.5`.
Tools take these as `league_key` / `team_key`; `list_leagues` discovers NBA league keys
(it takes no `game_code`; the client only builds the `nba` game).

## Security

OAuth secrets live in `.env`, `oauth2.json`, and related token files; these are gitignored.
Never commit them or print their contents.
