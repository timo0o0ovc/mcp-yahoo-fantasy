# MCP Yahoo Fantasy

An MCP (Model Context Protocol) server that wraps the
[Yahoo Fantasy Sports API](https://sports.yahoo.com/developer/), giving an LLM strictly read-only
access to your fantasy leagues across NFL, NHL, NBA, and MLB: standings, rosters,
matchups, players, stats, drafts, and transactions. It cannot change lineups, add/drop,
claim waivers, or respond to trades. For NBA 9-category head-to-head leagues it adds
schedule counts, recent-form projections, a 10k-run Monte Carlo matchup simulator, and
ranked move memos.

The server lives in [`yahoo/`](yahoo/). See [`yahoo/README.md`](yahoo/README.md) for setup
(authentication, configuration, and the full tool list).

## Quick start

```bash
./scripts/setup.sh          # install dependencies into yahoo/.venv via uv
cd yahoo && uv run yahoo-login   # one-time OAuth login (paste client id/secret, then a verifier code)
```

Then point your MCP client at the server (see `yahoo/README.md`).
