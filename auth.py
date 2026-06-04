"""
Gmail OAuth setup — run this once to get a refresh token.
Usage: python auth.py

Prerequisites:
1. Go to https://console.cloud.google.com
2. Create a project → Enable Gmail API
3. OAuth consent screen → External → Add your Gmail as test user
4. Credentials → OAuth 2.0 Client ID → Desktop app
5. Copy client_id and client_secret into accounts.yml under gmail:
6. Run: python auth.py
7. A browser window will open — sign in and approve access
8. The refresh_token is saved to accounts.yml automatically
"""

import sys
from pathlib import Path

import yaml
from google_auth_oauthlib.flow import InstalledAppFlow

ACCOUNTS_PATH = Path(__file__).parent / "accounts.yml"
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def main():
    with open(ACCOUNTS_PATH) as f:
        accounts = yaml.safe_load(f)

    gmail = accounts.get("gmail", {})

    if not gmail.get("client_id") or not gmail.get("client_secret"):
        print("Missing gmail.client_id or gmail.client_secret in accounts.yml")
        print("See the README for setup instructions.")
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": gmail["client_id"],
            "client_secret": gmail["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    print("\n=== Gmail OAuth Setup ===\n")
    print("A browser window will open for authorization.")
    print("Sign in with your Gmail account and approve access.\n")

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    if not creds.refresh_token:
        print("\nNo refresh_token received. Try revoking access at:")
        print("https://myaccount.google.com/permissions")
        print("Then run this again.\n")
        sys.exit(1)

    accounts["gmail"]["refresh_token"] = creds.refresh_token
    with open(ACCOUNTS_PATH, "w") as f:
        yaml.dump(accounts, f, default_flow_style=False)

    print("refresh_token saved to accounts.yml")
    print("You can now run: python service.py\n")


if __name__ == "__main__":
    main()
