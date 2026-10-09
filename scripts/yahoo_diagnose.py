"""Call Yahoo directly with the saved credentials and show the raw HTTP result.

Prints only status codes and Yahoo's error text, never tokens or secrets. Run from yahoo/:

    python ../scripts/yahoo_diagnose.py
"""

import re

from yahoo import auth

BASE = "https://fantasysports.yahooapis.com/fantasy/v2"
CHECKS = [
    ("NBA game lookup", f"{BASE}/game/nba?format=json"),
    ("Your games", f"{BASE}/users;use_login=1/games?format=json"),
    ("Your NBA leagues", f"{BASE}/users;use_login=1/games;game_codes=nba/leagues?format=json"),
]

sc = auth.session()
for label, url in CHECKS:
    r = sc.session.get(url)
    body = "" if r.ok else re.sub(r"\s+", " ", r.text)[:300]
    print(f"{label}: HTTP {r.status_code} {body}")
