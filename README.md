# 1A1 API client

Python client for the tenant-facing [1A1](https://demo.1a1.com) API. It requests an Entra app token, then uploads a transmittal letter and downloads JSON and GeoJSON for each document.

No third-party packages. Requires Python 3.10 or later.

## Setup

Copy the example env file and fill in the Entra values:

```powershell
copy .env.example .env
```

| Variable | Purpose |
| --- | --- |
| `TENANT_ID` | Entra directory (tenant) ID |
| `CLIENT_ID` | Application (client) ID |
| `CLIENT_SECRET` | Client secret value, not the secret ID |
| `SCOPE` | Token scope. Defaults to the API `/.default` scope |
| `APP_TOKEN` | Optional. When set, the script skips the Entra token request |
| `BASE_URL` | Platform host, for example `https://demo.1a1.com` |
| `PLATFORM_TENANT_ID` | Sent as `X-Platform-Tenant-Id` on client calls |
| `FILES` | Comma-separated paths uploaded by the menu default and by `all` |
| `UPLOAD_REQUEST_ID` | Default upload request id for the status prompt |
| `DOCUMENT_IDS` | Comma-separated document ids for the download prompts |
| `OUT` | Folder for downloaded files. Defaults to `out` |
| `WAIT` | Seconds to poll upload status before returning the latest snapshot |
| `TIMEOUT` | HTTP timeout in seconds. Defaults to `120` |
| `INSECURE` | `true` skips TLS verification (local dev only) |

`.env` and `out/` are gitignored.

## Run

Interactive menu. Pick a number, then the result prints and the menu returns.

```powershell
python simulate.py
```

| Choice | Call |
| --- | --- |
| 1 | `POST /api/v1/client/uploads` |
| 2 | `GET /api/v1/client/uploads/{uploadRequestId}/status` |
| 3 | `GET /api/v1/client/uploads` |
| 4 | `GET /api/v1/client/documents/{id}/json/{1\|2\|3}` |
| 5 | `GET /api/v1/client/documents/{id}/geojson/{1\|2\|3}` |
| 0 | Exit |

`PLATFORM_TENANT_ID` is required for every menu action.

Run the whole flow without prompts: upload `FILES`, poll status, list uploads, then save JSON and GeoJSON versions 1, 2, and 3 under `out/json` and `out/geojson`.

```powershell
python simulate.py all
```

Request only an Entra token. Values are typed at the prompt and the access token is printed.

```powershell
python get_token.py
```

## Library

`onea1_client.py` is the HTTP client. `OneA1Client` holds the app token and calls the platform. `OneA1Error` carries the method, URL, status, and response body.
