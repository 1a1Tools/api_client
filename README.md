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
| 4 | `GET /api/v1/client/documents/{id}/json/{fileVersion}` |
| 5 | `GET /api/v1/client/documents/{id}/geojson/{fileVersion}` |
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

## Downloads

Choices 4 and 5 ask for a document id and a file version. That version is a path segment on the download URL. It is separate from the `v1` in `/api/v1`, which is the API version. The JSON body has no version field.

### 1A1 JSON

`GET /api/v1/client/documents/{documentId}/json/{fileVersion}`

`fileVersion` is `1`, `2`, or `3`. Any other value returns 400. A document outside the tenant, or a version with no content, returns 404.

The response file is named `1A1_v{fileVersion}_{documentName}.json`. The client saves that name, so the version is visible on the file as well as in the URL.

| Version | What you get |
| --- | --- |
| 1 | Name and value parameters, under airport, document type, procedure, and structure |
| 2 | Named blocks. A block holds parameters (name and value), rows, or tables. No page or position |
| 3 | The same blocks as version 2. Each parameter also has page, line, group, and position |

Version 2 and version 3 are the two block formats. Use the path segment, or the `1A1_v2_` / `1A1_v3_` file prefix, to tell them apart.

### GeoJSON

`GET /api/v1/client/documents/{documentId}/geojson/{fileVersion}`

| Version | Converter | Notes |
| --- | --- | --- |
| 1 | GeoJSON | Procedure plate |
| 2 | GeoJSON-V2 | Procedure plate |
| 3 | GeoJSON-V3 | Reads the stored AIP model. A transmittal-letter procedure plate has no AIP model, so this version is for AIP documents. Returns 404 when that model is missing |

The GeoJSON file name is the document name plus the converter extension. It does not include the version. The version you asked for is only in the URL. The menu writes these files under `out/geojson`.

## Library

`onea1_client.py` is the HTTP client. `OneA1Client` holds the app token and calls the platform. `OneA1Error` carries the method, URL, status, and response body.
