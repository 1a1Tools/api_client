"""Menu for the tenant-facing 1A1 API.

On start, loads .env. If APP_TOKEN is empty, requests an Entra bearer token
and sends that token on every API call.
Then prints a numbered menu. Type a number and press Enter. The result is
printed, then the menu is printed again.

    python simulate.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from onea1_client import OneA1Client, OneA1Error

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
DEFAULT_SCOPE = "api://cd5136f7-4058-42f5-b28b-bb6cfb8f1802/.default"
VERSIONS = (1, 2, 3)


class Session:
    def __init__(self, env: dict[str, str]) -> None:
        self.env = env
        self.scope = env.get("SCOPE") or DEFAULT_SCOPE
        self.files = _split(env.get("FILES", ""))
        self.upload_request_id = env.get("UPLOAD_REQUEST_ID", "")
        self.document_ids = _split(env.get("DOCUMENT_IDS", ""))
        self.wait = float(env.get("WAIT") or 0)
        self.out = _resolve(env.get("OUT") or "out")
        insecure = env.get("INSECURE", "true").lower() in {"1", "true", "yes"}
        timeout = float(env.get("TIMEOUT") or 120)
        self.client = OneA1Client(env.get("BASE_URL") or "https://localhost:7193", insecure=insecure, timeout=timeout)
        self.client.app_token = env.get("APP_TOKEN") or None
        self.client.access_token = self.client.app_token
        self.client.platform_tenant_id = env.get("PLATFORM_TENANT_ID") or None

    def ensure_app_token(self) -> None:
        if self.client.app_token:
            self.client.access_token = self.client.app_token
            print("App token: loaded from .env")
            return
        for key in ("TENANT_ID", "CLIENT_ID", "CLIENT_SECRET"):
            if not self.env.get(key):
                raise ValueError(f"{key} is missing from .env.")
        issued = self.client.get_token(self.env["TENANT_ID"], self.env["CLIENT_ID"], self.env["CLIENT_SECRET"], self.scope)
        print(f"Entra token: created, {issued.get('token_type')}, expires in {issued.get('expires_in')}s")


def main() -> int:
    env = _load_env(ENV_PATH)
    print(f"Loaded {ENV_PATH.name}")
    session = Session(env)
    session.ensure_app_token()
    if len(sys.argv) > 1 and sys.argv[1] == "all":
        _run_all(session)
        return 0

    actions = {
        "1": ("Upload a file", _upload),
        "2": ("Check status", _status),
        "3": ("List uploads", _list_uploads),
        "4": ("Download JSON", _download_json),
        "5": ("Download GeoJSON", _download_geojson),
    }
    while True:
        _print_menu(session, actions)
        choice = input("Choice: ").strip()
        if choice == "0":
            return 0
        action = actions.get(choice)
        if action is None:
            print("Unknown choice.")
            continue
        print()
        try:
            action[1](session)
        except (OneA1Error, ValueError) as error:
            print(error)


def _print_menu(session: Session, actions: dict[str, tuple[str, object]]) -> None:
    request_label = session.upload_request_id or "(none)"
    print()
    print(f"Upload request: {request_label}")
    print()
    for number, (label, _) in actions.items():
        print(f"{number}. {label}")
    print("0. Exit")


def _run_all(session: Session) -> None:
    """Upload the default file, then status, list, JSON, and GeoJSON."""
    _require_platform_tenant(session)
    paths = [_resolve(path) for path in session.files]
    missing = [str(path) for path in paths if not path.is_file()]
    if not paths or missing:
        raise ValueError("File not found: " + ", ".join(missing or ["(none)"]))
    uploaded = session.client.upload(*paths)
    session.upload_request_id = str(uploaded["uploadRequestId"])
    print(f"upload request id: {session.upload_request_id}")
    print(f"status url: {uploaded.get('statusUrl')}")
    _print_request_id(session.client)
    for item in uploaded.get("documents") or []:
        document_id = str(item.get("id") or "")
        print(f"document {document_id}  {item.get('name')}")
        if document_id and document_id not in session.document_ids:
            session.document_ids.append(document_id)
    snapshot = _poll_status(session.client, session.upload_request_id, session.client.timeout)
    print(f"state: {snapshot.get('state')}  {snapshot.get('percentComplete')}%")
    _list_uploads(session)
    if not session.document_ids:
        print("No document ids to download.")
        return
    print("Downloading 1A1 JSON versions 1, 2, and 3")
    for document_id in list(session.document_ids):
        for version in VERSIONS:
            _save(session.client, session.client.download_json, document_id, version, session.out / "json", "json")
    print("Downloading GeoJSON versions 1, 2, and 3")
    for document_id in list(session.document_ids):
        for version in VERSIONS:
            _save(session.client, session.client.download_geojson, document_id, version, session.out / "geojson", "geojson")


def _require_platform_tenant(session: Session) -> None:
    if not session.client.platform_tenant_id:
        raise ValueError("PLATFORM_TENANT_ID is missing from .env.")


def _upload(session: Session) -> None:
    _require_platform_tenant(session)
    default = ", ".join(session.files)
    raw = _ask("File", default)
    paths = [_resolve(part) for part in _split(raw)]
    if not paths:
        print("Enter a file path.")
        return
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        print("File not found: " + ", ".join(missing))
        return
    uploaded = session.client.upload(*paths)
    session.upload_request_id = str(uploaded["uploadRequestId"])
    session.files = [str(path) for path in paths]
    print(f"upload request id: {session.upload_request_id}")
    print(f"status url: {uploaded.get('statusUrl')}")
    _print_request_id(session.client)
    for item in uploaded.get("documents") or []:
        document_id = str(item.get("id") or "")
        print(f"document {document_id}  {item.get('name')}")
        if document_id and document_id not in session.document_ids:
            session.document_ids.append(document_id)


def _status(session: Session) -> None:
    _require_platform_tenant(session)
    upload_request_id = _ask("Upload request id", session.upload_request_id)
    if not upload_request_id:
        print("Enter an upload request id.")
        return
    session.upload_request_id = upload_request_id
    snapshot = _poll_status(session.client, upload_request_id, session.wait)
    print(f"state: {snapshot.get('state')}  {snapshot.get('percentComplete')}%")
    print(_pretty(snapshot))


def _list_uploads(session: Session) -> None:
    _require_platform_tenant(session)
    files = session.client.uploads()
    print(f"{len(files)} file(s)")
    _print_request_id(session.client)
    for item in files:
        children = item.get("children") or []
        child_ids = [str(child.get("documentId")) for child in children if child.get("documentId")]
        print(
            f"{item.get('name')}  id={item.get('documentId')}  "
            f"request={item.get('uploadRequestId')}  state={item.get('state')}  "
            f"children={len(child_ids)}"
        )
        for document_id in child_ids:
            if document_id not in session.document_ids:
                session.document_ids.append(document_id)


def _download_json(session: Session) -> None:
    _download(session, session.client.download_json, session.out / "json", "json")


def _download_geojson(session: Session) -> None:
    _download(session, session.client.download_geojson, session.out / "geojson", "geojson")


def _download(session: Session, download, folder: Path, kind: str) -> None:
    _require_platform_tenant(session)
    default_ids = ", ".join(session.document_ids)
    raw = _ask("Document id", default_ids)
    document_ids = _split(raw)
    if not document_ids:
        print("Enter a document id.")
        return
    version_text = _ask("Version", "1,2,3")
    versions = _versions(version_text)
    session.document_ids = document_ids
    for document_id in document_ids:
        for version in versions:
            _save(session.client, download, document_id, version, folder, kind)


def _poll_status(client: OneA1Client, upload_request_id: str, wait_seconds: float) -> dict:
    deadline = time.monotonic() + wait_seconds
    while True:
        snapshot = client.status(upload_request_id)
        _print_request_id(client)
        if snapshot.get("state") in {"completed", "failed"} or time.monotonic() >= deadline:
            return snapshot
        time.sleep(2)


def _save(client: OneA1Client, download, document_id: str, version: int, folder: Path, kind: str) -> None:
    label = f"{kind} v{version}  {document_id}"
    try:
        path = download(document_id, version, folder)
    except OneA1Error as error:
        request_id = error.request_id or client.last_request_id or ""
        print(f"{label}  HTTP {error.status}: {_short(error.body)}  X-Request-Id: {request_id}")
        return
    print(f"{label}  saved {path}  X-Request-Id: {client.last_request_id}")


def _print_request_id(client: OneA1Client) -> None:
    if client.last_request_id:
        print(f"X-Request-Id: {client.last_request_id}")


def _load_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError(f"Missing {path}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _ask(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    return input(f"{label}{suffix}: ").strip() or default


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _versions(value: str) -> list[int]:
    versions: list[int] = []
    for part in _split(value):
        version = int(part)
        if version not in VERSIONS:
            raise ValueError("Version must be 1, 2, or 3.")
        versions.append(version)
    if not versions:
        raise ValueError("Enter a version.")
    return versions


def _resolve(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    return candidate


def _pretty(value: object) -> str:
    return json.dumps(value, indent=2)


def _short(body: str) -> str:
    text = body.strip().replace("\n", " ")
    if text.startswith("{") or text.startswith("["):
        try:
            text = json.dumps(json.loads(text), separators=(",", ":"))
        except json.JSONDecodeError:
            pass
    return text if len(text) <= 180 else text[:180] + "..."


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OneA1Error as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
    except KeyboardInterrupt:
        print()
        raise SystemExit(0)
