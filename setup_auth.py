"""
Run this ONCE locally to generate the OAuth token.
Then copy the printed JSON into GitHub Secrets as GMAIL_TOKEN_JSON.

Usage:
  1. Download credentials.json from Google Cloud Console
     (APIs & Services → Credentials → OAuth 2.0 Client → Download JSON)
  2. pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
  3. python setup_auth.py
  4. A browser window will open — authorize the app
  5. Copy the printed token JSON into your GitHub repo secret GMAIL_TOKEN_JSON
"""

import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

def main():
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(port=0)

    token_json = creds.to_json()
    print("\n✅ Auth successful! Copy this JSON into your GitHub Secret GMAIL_TOKEN_JSON:\n")
    print(token_json)

    # Also save locally for testing
    with open("token.json", "w") as f:
        f.write(token_json)
    print("\n(Also saved to token.json for local testing)")


if __name__ == "__main__":
    main()
