"""Client for the tenant-facing 1A1 API.

The app token comes from Entra. Everything else is under /api/v1:

- POST login.microsoftonline.com/{tenant}/oauth2/v2.0/token   client credentials
- POST /tenants/{tenantId}/clients          app token, secret returned once
- POST /client/token                        client id and secret
- POST /client/uploads                      TL file, returns an upload request id
- GET  /client/uploads/{uploadRequestId}/status
- GET  /client/uploads                      files, status, and child document ids
- GET  /client/documents/{id}/json/{1|2|3}
- GET  /client/documents/{id}/geojson/{1|2|3}
"""

from __future__ import annotations

import json
import mimetypes
import ssl
import uuid
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode


class OneA1Error(Exception):
    def __init__(self, method: str, url: str, status: int, body: str) -> None:
        self.method = method
        self.url = url
        self.status = status
        self.body = body
        preview = body if len(body) <= 500 else body[:500] + "..."
        super().__init__(f"{method} {url} -> {status}: {preview}")


class OneA1Client:
    """Talks to one platform host. Client endpoints send the Entra bearer token."""

    def __init__(self, base_url: str, *, insecure: bool = False, timeout: float = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._ssl = ssl._create_unverified_context() if insecure else None
        self.app_token: str | None = None
        self.access_token: str | None = None
        self.client_id: str | None = None
        self.client_secret: str | None = None
        self.tenant_id: str | None = None
        self.platform_tenant_id: str | None = None

    def get_token(
        self,
        azure_tenant_id: str,
        client_id: str,
        client_secret: str,
        scope: str,
    ) -> dict[str, Any]:
        """POST the Entra client-credentials endpoint. Stores the access token as the app token."""
        if "/" in azure_tenant_id or "\\" in azure_tenant_id:
            raise ValueError("azure tenant id must be a single path segment.")
        url = f"https://login.microsoftonline.com/{azure_tenant_id}/oauth2/v2.0/token"
        body = urlencode(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": scope,
                "grant_type": "client_credentials",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            response = urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise OneA1Error("POST", url, error.code, detail) from None
        except urllib.error.URLError as error:
            raise OneA1Error("POST", url, 0, str(error.reason)) from None
        issued = json.loads(response.read().decode("utf-8"))
        self.app_token = str(issued["access_token"])
        self.access_token = self.app_token
        return issued

    def create_client(self, tenant_id: str, app_token: str) -> dict[str, Any]:
        """POST /api/v1/tenants/{tenantId}/clients. The secret is only in this response."""
        created = self._json(
            "POST",
            f"/api/v1/tenants/{quote(tenant_id)}/clients",
            token=app_token,
            ok=(201,),
        )
        self.app_token = app_token
        self.tenant_id = str(created.get("tenantId") or tenant_id)
        self.client_id = str(created["clientId"])
        self.client_secret = str(created["clientSecret"])
        return created

    def token(self, client_id: str | None = None, client_secret: str | None = None) -> dict[str, Any]:
        """POST /api/v1/client/token."""
        client_id = client_id or self.client_id
        client_secret = client_secret or self.client_secret
        if not client_id or not client_secret:
            raise ValueError("client id and client secret are required.")
        issued = self._json(
            "POST",
            "/api/v1/client/token",
            payload={"client_id": client_id, "client_secret": client_secret},
            ok=(200,),
        )
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = str(issued["access_token"])
        return issued

    def upload(self, *paths: str | Path) -> dict[str, Any]:
        """POST /api/v1/client/uploads. Returns 202 with uploadRequestId."""
        if not paths:
            raise ValueError("At least one TL file is required.")
        boundary = "----OneA1" + uuid.uuid4().hex
        body = _multipart(boundary, paths)
        return self._json(
            "POST",
            "/api/v1/client/uploads",
            token=self._client_token(),
            data=body,
            content_type=f"multipart/form-data; boundary={boundary}",
            ok=(202,),
        )

    def status(self, upload_request_id: str) -> dict[str, Any]:
        """GET /api/v1/client/uploads/{uploadRequestId}/status."""
        return self._json(
            "GET",
            f"/api/v1/client/uploads/{quote(upload_request_id)}/status",
            token=self._client_token(),
            ok=(200,),
        )

    def uploads(self) -> list[dict[str, Any]]:
        """GET /api/v1/client/uploads. Each file includes its child document ids."""
        listed = self._json(
            "GET",
            "/api/v1/client/uploads",
            token=self._client_token(),
            ok=(200,),
        )
        if not isinstance(listed, list):
            raise OneA1Error("GET", self.base_url + "/api/v1/client/uploads", 200, "Expected a list of uploads.")
        return listed

    def download_json(self, document_id: str, version: int, destination: str | Path) -> Path:
        """GET /api/v1/client/documents/{id}/json/{version}. Version is 1, 2, or 3."""
        return self._download(
            f"/api/v1/client/documents/{quote(document_id)}/json/{version}",
            destination,
            fallback=f"1A1_v{version}_{document_id}.json",
        )

    def download_geojson(self, document_id: str, version: int, destination: str | Path) -> Path:
        """GET /api/v1/client/documents/{id}/geojson/{version}. Version is 1, 2, or 3."""
        return self._download(
            f"/api/v1/client/documents/{quote(document_id)}/geojson/{version}",
            destination,
            fallback=f"{document_id}.v{version}.geojson",
        )

    def _client_token(self) -> str:
        if not self.access_token:
            raise ValueError("An Entra bearer token is required.")
        return self.access_token

    def _download(self, path: str, destination: str | Path, fallback: str) -> Path:
        response = self._open("GET", path, token=self._client_token(), ok=(200,))
        folder = Path(destination)
        folder.mkdir(parents=True, exist_ok=True)
        name = _filename(response.headers.get("Content-Disposition")) or fallback
        target = folder / name
        target.write_bytes(response.read())
        return target

    def _json(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        payload: dict[str, Any] | None = None,
        data: bytes | None = None,
        content_type: str | None = None,
        ok: tuple[int, ...],
    ) -> Any:
        body = data
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            content_type = "application/json"
        response = self._open(method, path, token=token, data=body, content_type=content_type, ok=ok)
        raw = response.read()
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def _open(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        data: bytes | None = None,
        content_type: str | None = None,
        ok: tuple[int, ...],
    ) -> Any:
        url = self.base_url + path
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if self.platform_tenant_id and path.startswith("/api/v1/client/"):
            headers["X-Platform-Tenant-Id"] = self.platform_tenant_id
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            return urllib.request.urlopen(request, timeout=self.timeout, context=self._ssl)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            if error.code not in ok:
                raise OneA1Error(method, url, error.code, detail) from None
            return error
        except urllib.error.URLError as error:
            raise OneA1Error(method, url, 0, str(error.reason)) from None


def _multipart(boundary: str, paths: tuple[str | Path, ...]) -> bytes:
    chunks: list[bytes] = []
    for path in paths:
        file_path = Path(path)
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/pdf"
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files"; filename="{file_path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        )
        chunks.append(header.encode("utf-8"))
        chunks.append(file_path.read_bytes())
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks)


def _filename(content_disposition: str | None) -> str | None:
    if not content_disposition:
        return None
    marker = "filename="
    lower = content_disposition.lower()
    start = lower.find(marker)
    if start < 0:
        return None
    value = content_disposition[start + len(marker):].split(";", 1)[0].strip().strip('"')
    name = Path(value).name
    return name or None
