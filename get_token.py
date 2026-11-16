"""Request an Entra app token. Paste each value when prompted.

The client id is the Application (client) ID on the app Overview page.
The client secret is the secret Value, not the Secret ID.

    python get_token.py
"""

from __future__ import annotations

import sys

from onea1_client import OneA1Client, OneA1Error

DEFAULT_SCOPE = "api://cd5136f7-4058-42f5-b28b-bb6cfb8f1802/.default"


def main() -> int:
    azure_tenant_id = _ask("Directory (tenant) ID")
    client_id = _ask("Application (client) ID")
    client_secret = _ask("Client secret value")
    scope = input(f"Scope [{DEFAULT_SCOPE}]: ").strip() or DEFAULT_SCOPE

    client = OneA1Client("https://login.microsoftonline.com", timeout=30)
    issued = client.get_token(azure_tenant_id, client_id, client_secret, scope)
    print(f"token type: {issued.get('token_type')}  expires in: {issued.get('expires_in')}s")
    print(issued["access_token"])
    return 0


def _ask(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print("Paste a value.")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OneA1Error as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
