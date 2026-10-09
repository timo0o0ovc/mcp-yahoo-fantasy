# MCP Yahoo Fantasy

An MCP server for Yahoo Fantasy Sports. It wraps
[`yahoo_fantasy_api`](https://github.com/spilchen/yahoo_fantasy_api) and exposes its reads
and writes as MCP tools, for NBA leagues only (Yahoo game code `nba`).

## How it works

- **Data**: all tools call `yahoo_fantasy_api`, which returns plain JSON the model consumes
  directly.
- **Auth**: Yahoo uses three-legged OAuth2. You authorize once with `uv run yahoo-login`,
  which saves your credentials (one Yahoo app, one long-lived refresh token) to a `.env`
  file. The server loads `.env` on startup and bridges those credentials into the
  `oauth2.json` that `yahoo_fantasy_api` reads. The access token is refreshed automatically,
  so the server runs unattended after the one-time login.

## Setup

1. **Register a Yahoo app** at <https://developer.yahoo.com/apps/create/>.
   - Set the application to **Confidential Client** with **Fantasy Sports: Read/Write**
     permission.
   - Set the redirect URI to `https://localhost:8000`.
   - Note the **Client ID** (consumer key) and **Client Secret** (consumer secret).

2. **Install dependencies** (from the repo root): `./scripts/setup.sh`, or from here:

   ```bash
   uv sync
   ```

3. **Log in once** to mint a refresh token:

   ```bash
   uv run yahoo-login --client-id <id> --client-secret <secret>
   ```

   (Flags are optional -- without them you'll be prompted, or they're read from `.env`.)
   Open the printed URL, approve access, and paste back the verifier code Yahoo shows you.
   This writes your credentials to `.env` in the current directory. Run the server from that
   same directory, or point `YAHOO_ENV_FILE` at the file (see below).

   On first use the server reads `.env` and writes a refreshed
   `~/.config/yahoo-fantasy-mcp/oauth2.json`; subsequent runs reuse and auto-refresh it.

## Configuration (environment variables)

All are optional:

| Variable | Purpose |
| --- | --- |
| `YAHOO_LEAGUE_KEY` | Default league key (e.g. `449.l.365083`) so tools can omit `league_key`. Find it with the `list_leagues` tool. |
| `YAHOO_ENV_FILE` | Path to the `.env` written by `yahoo-login`, if the server doesn't run from the directory it was created in (default `./.env`). |
| `YAHOO_OAUTH_FILE` | Path to the bridged `oauth2.json` (default `~/.config/yahoo-fantasy-mcp/oauth2.json`). |
| `YAHOO_MCP_CONFIG_DIR` | Directory for the default `oauth2.json` location. |
| `YAHOO_CONSUMER_KEY` / `YAHOO_CONSUMER_SECRET` / `YAHOO_ACCESS_TOKEN` / `YAHOO_REFRESH_TOKEN` | The credentials `yahoo-login` writes to `.env`; set them directly instead if you prefer (e.g. in your MCP client config). |

## Connecting an MCP client

Add the server to your client config (e.g. Claude Desktop's `claude_desktop_config.json`),
using an absolute path:

```jsonc
{
  "mcpServers": {
    "yahoo": {
      "command": "uv",
      "args": ["--directory", "/ABSOLUTE/PATH/TO/mcp-yahoo-fantasy/yahoo", "run", "yahoo"],
      "env": {
        "YAHOO_LEAGUE_KEY": "449.l.365083",
        "YAHOO_ENV_FILE": "/ABSOLUTE/PATH/TO/.env"
      }
    }
  }
}
```

Debug interactively with the MCP Inspector: `../scripts/debug.sh` (run from this directory).

## Tools

League reads: `list_leagues`, `league_settings`, `league_standings`, `league_teams`,
`league_matchups`, `league_draft_results`, `league_transactions`, `league_stat_categories`,
`league_roster_positions`, `current_week`.

Player reads: `free_agents`, `waivers`, `taken_players`, `player_details`, `player_stats`,
`percent_owned`.

Team reads: `my_team_key`, `team_details`, `team_roster`, `team_matchup_opponent`,
`proposed_trades`.

Analytics (NBA 9-cat H2H): `games_this_week`, `player_projection`, `sim_matchup`,
`recommend_moves` -- see below.

Most tools accept an optional `league_key`/`team_key`; without them they fall back to
`YAHOO_LEAGUE_KEY` and to your own team in that league.

## Read-only fork

This fork exposes **no write tools**. Lineup changes, add/drop, waiver claims and trade
accept/reject were removed. Three layers enforce it:

1. `server.py` registers tools only through `read_tool()`, which sets
   `readOnlyHint=True, destructiveHint=False` on every tool.
2. `client.py` hands tools `ReadOnlyTeam` / `ReadOnlyLeague` proxies that raise
   `ReadOnlyViolation` on any mutating `yahoo_fantasy_api` method.
3. `readonly.lock_yhandler()` disables `YHandler.put/post` (and their helpers) process-wide.

`tests/test_read_only.py` fails if any write tool is registered, if a tool name reads like a
write, if a tool lacks the read-only annotation, if any source file calls a Yahoo write
method, or if the tool set differs from the reviewed allowlist. You can also set the Yahoo
app permission to **Fantasy Sports: Read** for a fourth, server-side layer.

## Analytics (`src/yahoo/analytics/`)

Built for a Yahoo 9-category head-to-head NBA league: FG%, FT%, 3PM, PTS, REB, AST, STL,
BLK, TO (lower wins). Live data comes from `nba_api` (stats.nba.com) and Yahoo.

| Tool | What it returns |
| --- | --- |
| `games_this_week` | Regular-season games per NBA team in a Yahoo week (official schedule), remaining games from a date, 4+ game teams, games per day. Preseason, All-Star and NBA Cup final ids are excluded. |
| `player_projection` | Per-game line from the last **14- and 30-day** windows of the **current season** (60/40 blend). Rows from other seasons or older than 30 days are discarded. Includes a dated role check. |
| `sim_matchup` | 10,000-run Monte Carlo of the week: win/tie/loss probability, expected category wins, per-category win rates, assumptions and sources. Uses rosters, schedule from today (US Eastern), daily active slots and Yahoo week-to-date totals. |
| `recommend_moves` | Ranked decision memos for add/drop moves. Recommends only; never executes. |

### Role verification

A player's role is `verified` only if team, role/minutes and injury status each have a
source dated within **14 days** (recent game logs, today's Yahoo status, today's NBA player
directory, or dated `extra_evidence` you pass from news). Otherwise it is labelled
exactly **`role unverified`**, with the failing reasons. Last season's role is never used:
a player with no current-season games in 30 days gets no projection unless you pass a
`manual_lines` entry, which is labelled as an assumption and still `role unverified`.

### Simulation model

- Per game: a shared minutes factor (Gamma, mean 1) drives FGA, 3PA share, FTA and
  Poisson REB/AST/STL/BLK/TOV. Makes are Binomial on attempts, and PTS =
  2*2PM + 3*3PM + FTM, so points, threes and percentages stay consistent.
- Shooting % per simulation: Beta posterior of the recent sample shrunk to league priors.
- Team FG%/FT% = summed makes / summed attempts, compared at 3 decimals.
- Availability by Yahoo status: healthy 0.93, GTD/DTD 0.55, O/INJ/NA 0 (override with
  `availability`). IL-slot players are excluded.
- Daily slot cap fills the highest-value players who play; positional eligibility is
  ignored (slightly optimistic for both sides).
- Moves use common random numbers, so deltas isolate the move.

### Decision memo fields

`action`, `delta_win_prob` (+ std error), `delta_expected_category_wins`,
`per_category_win_rates` (before/after/delta for all 9), `assumptions`,
`role_and_injury_sources` (role status, team, 14-day minutes, injury status and every
source with its date and age for both players), `role_flag`, `confidence`
(`high`/`medium`/`low`) and `confidence_reasons`. Confidence is `low` whenever a role is
unverified, the sample is under 3 games, or the effect is within 2 standard errors.

### Tests

```bash
uv run pytest
```

Tests use fixtures and stubs; no Yahoo credentials or network needed.

> Note: proposing trades is intentionally omitted -- `yahoo_fantasy_api`'s `propose_trade`
> is broken upstream (its argument handling is inconsistent with its own helper). Accepting
> and rejecting trades works.
