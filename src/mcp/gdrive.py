"""Google Drive upload helper for the Telegram MCP server.

Uploads a local file to the user's Google Drive, makes it readable by
anyone with the link, and returns the public share URL.

Credentials
-----------
- OAuth client JSON (downloaded from Google Cloud Console -> APIs &
  Services -> Credentials -> OAuth client ID, "Desktop app" type)
  is expected at ``config/gdrive_client.json``.
- Refresh token is persisted at ``config/gdrive_token.json`` after the
  one-time browser authorization. Subsequent uploads run headless.

First-time setup
----------------
Run ``python -m src.mcp.gdrive`` (no arguments). A browser window opens
for Google sign-in; consent grants the bot ``drive.file`` scope (write
only to files the bot creates, no access to the rest of your Drive).
On success, ``gdrive_token.json`` is written and uploads work headless
from then on.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Optional

# OAuth scope: drive.file gives the app access only to files it creates
# or that the user explicitly opens with this app. Safer than full drive
# scope -- the bot cannot read or delete arbitrary files in your Drive.
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLIENT_SECRETS_PATH = _PROJECT_ROOT / "config" / "gdrive_client.json"
TOKEN_PATH = _PROJECT_ROOT / "config" / "gdrive_token.json"


class GDriveError(RuntimeError):
    """Raised when a Google Drive upload cannot complete."""


def _load_credentials():
    """Load and refresh OAuth credentials, running the install-flow once
    if no valid token is cached yet.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds: Optional[Credentials] = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception:
            creds = None  # fall through to interactive flow

    if not CLIENT_SECRETS_PATH.exists():
        raise GDriveError(
            f"Google Drive OAuth client JSON not found at "
            f"{CLIENT_SECRETS_PATH}. Create one in Google Cloud Console "
            f"(APIs & Services -> Credentials -> OAuth client ID, Desktop "
            f"app) and place the downloaded file at that path."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_PATH), SCOPES)
    # Opens a browser window. Used only on first run / when refresh fails.
    creds = flow.run_local_server(port=0, open_browser=True)
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def upload_and_share(file_path: Path, caption: str = "") -> str:
    """Upload *file_path* to Google Drive, share by link, return URL.

    Raises GDriveError on any failure (missing creds, API error, etc.).
    """
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    if not file_path.exists() or not file_path.is_file():
        raise GDriveError(f"file not found: {file_path}")

    creds = _load_credentials()
    service = build("drive", "v3", credentials=creds, cache_discovery=False)

    mime, _ = mimetypes.guess_type(str(file_path))
    if not mime:
        mime = "application/octet-stream"

    media = MediaFileUpload(str(file_path), mimetype=mime, resumable=False)
    metadata = {"name": file_path.name}
    if caption:
        metadata["description"] = caption[:1024]

    try:
        created = (
            service.files()
            .create(body=metadata, media_body=media, fields="id,webViewLink")
            .execute()
        )
    except Exception as e:
        raise GDriveError(f"upload failed: {e}") from e

    file_id = created.get("id")
    if not file_id:
        raise GDriveError("upload succeeded but no file id returned")

    # Make readable by anyone with the link
    try:
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
            fields="id",
        ).execute()
    except Exception as e:
        raise GDriveError(f"share permission failed: {e}") from e

    # Prefer webViewLink (opens Drive viewer); fall back to direct URL
    link = created.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"
    return link


if __name__ == "__main__":
    # Bootstrap helper: run once to perform interactive auth and cache
    # the refresh token. After this, the MCP tool works headless.
    creds = _load_credentials()
    print(f"OAuth OK. Token cached at: {TOKEN_PATH}")
    print(f"Scopes: {creds.scopes}")
