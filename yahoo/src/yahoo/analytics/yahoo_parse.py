"""
Pull week-to-date category totals for one team out of Yahoo's raw scoreboard JSON
(League.matchups(week)). Yahoo NBA stat ids are fixed; FG%/FT% are rebuilt from the
makes/attempts stats (9004003 "FGM/FGA", 9007006 "FTM/FTA"), never from the displayed %.
"""

YAHOO_NBA_STAT_IDS = {
    "10": "FG3M",
    "12": "PTS",
    "15": "REB",
    "16": "AST",
    "17": "STL",
    "18": "BLK",
    "19": "TOV",
}
MAKES_ATTEMPTS = {"9004003": ("FGM", "FGA"), "9007006": ("FTM", "FTA")}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0  # Yahoo shows "-" before any games


def _team_blocks(node):
    """Yield every Yahoo 'team' list (metadata list + sub-resources) in the tree."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "team" and isinstance(v, list):
                yield v
            yield from _team_blocks(v)
    elif isinstance(node, list):
        for v in node:
            yield from _team_blocks(v)


def _team_key(block):
    meta = block[0] if block and isinstance(block[0], list) else []
    for item in meta:
        if isinstance(item, dict) and "team_key" in item:
            return item["team_key"]
    return None


def _stats(block):
    for part in block[1:]:
        if isinstance(part, dict) and "team_stats" in part:
            return part["team_stats"].get("stats", [])
    return None


def week_totals(scoreboard_raw, team_key):
    """Totals keyed like analytics.categories.TOTAL_FIELDS, or None if not found."""
    for block in _team_blocks(scoreboard_raw):
        if _team_key(block) != team_key:
            continue
        stats = _stats(block)
        if stats is None:
            continue
        out = {}
        for s in stats:
            stat = s.get("stat", s)
            sid, val = str(stat.get("stat_id")), stat.get("value")
            if sid in MAKES_ATTEMPTS:
                m_key, a_key = MAKES_ATTEMPTS[sid]
                made, _, att = str(val or "").partition("/")
                out[m_key], out[a_key] = _num(made), _num(att)
            elif sid in YAHOO_NBA_STAT_IDS:
                out[YAHOO_NBA_STAT_IDS[sid]] = _num(val)
        return out
    return None
