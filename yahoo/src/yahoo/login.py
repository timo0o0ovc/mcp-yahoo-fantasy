"""
One-time Yahoo authorization for the MCP server.

Runs Yahoo's OAuth2 flow through `yahoo_oauth` (the same library the server uses to refresh
tokens) and saves the resulting credentials to `.env`, which the server loads on startup.
The flow is out-of-band: open the printed URL, approve access, and Yahoo shows a verifier
code that you paste back here.

    uv run yahoo-login --client-id <id> --client-secret <secret>

Client id/secret come from your Yahoo app at https://developer.yahoo.com/apps/. They fall
back to $YAHOO_CONSUMER_KEY/$YAHOO_CONSUMER_SECRET, then to whatever is already in `.env`,
then to an interactive prompt.
"""

import argparse
import getpass
import json
import os

from yahoo_oauth import OAuth2

from .auth import ENV_FILE, load_env_file, write_env


class _VerboseOAuth2(OAuth2):
    """OAuth2 that reports Yahoo's error instead of a bare KeyError when the code exchange
    is rejected (bad/expired/reused code, wrong secret, redirect URI mismatch)."""

    def handler(self):
        """Run the normal flow, adding `scope=<self.scope>` to the authorize URL if set."""
        scope = vars(self).get("scope")
        if scope:
            original = self.oauth.get_authorize_url
            self.oauth.get_authorize_url = lambda **params: original(scope=scope, **params)
        return super().handler()

    def oauth2_access_parser(self, raw_access):
        try:
            body = json.loads(raw_access.content.decode("utf-8"))
        except ValueError:
            body = {}
        if "access_token" not in body:
            raise SystemExit(
                f"Yahoo rejected the login (HTTP {raw_access.status_code}): "
                f"{body.get('error', 'unknown error')} - "
                f"{body.get('error_description', 'no description')}\n"
                "Common causes: the verifier code was mistyped, expired or already used "
                "(get a new one by re-running yahoo-login); wrong Client ID/Secret; or the "
                "app's redirect URI doesn't match."
            )
        return super().oauth2_access_parser(raw_access)


def main():
    parser = argparse.ArgumentParser(
        prog="yahoo-login", description="Authorize the Yahoo Fantasy MCP server."
    )
    parser.add_argument("--client-id", help="Yahoo app Client ID (Consumer Key).")
    parser.add_argument("--client-secret", help="Yahoo app Client Secret (Consumer Secret).")
    parser.add_argument(
        "--scope",
        help="Optional OAuth scope to add to the authorize URL (e.g. fspt-r). Normally "
        "unneeded: Yahoo ties Fantasy access to the app's settings.",
    )
    args = parser.parse_args()

    load_env_file()
    client_id = (
        args.client_id
        or os.environ.get("YAHOO_CONSUMER_KEY")
        or input("Yahoo Client ID: ").strip()
    )
    client_secret = (
        args.client_secret
        or os.environ.get("YAHOO_CONSUMER_SECRET")
        or getpass.getpass("Yahoo Client Secret: ").strip()
    )

    # browser_callback=False prints the authorization URL in the prompt (robust on headless
    # / WSL where auto-opening a browser silently fails) and reads the verifier code. The
    # OAuth2 constructor runs the whole exchange; store_file=False stops it writing its own
    # secrets.json -- we persist to .env instead.
    print("Open this URL, approve access, then paste the verifier code Yahoo shows you.\n")
    oauth = _VerboseOAuth2(
        client_id, client_secret, browser_callback=False, store_file=False, scope=args.scope
    )

    write_env(
        {
            "YAHOO_CONSUMER_KEY": client_id,
            "YAHOO_CONSUMER_SECRET": client_secret,
            "YAHOO_ACCESS_TOKEN": oauth.access_token,
            "YAHOO_REFRESH_TOKEN": oauth.refresh_token,
        }
    )
    # The server rebuilds oauth2.json from .env on startup, so a fresh login just works.
    print(f"\nSaved Yahoo credentials to {ENV_FILE}. Start the server with: uv run yahoo")
