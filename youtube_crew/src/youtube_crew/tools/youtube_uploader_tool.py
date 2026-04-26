from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from pydantic import BaseModel, Field

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeUploadInput(BaseModel):
    video_path: str = Field(..., description="Path to the video file to upload.")
    video_title: str = Field(..., description="YouTube video title.")
    description: str = Field(default="", description="YouTube video description.")
    category_id: str = Field(default="22", description="YouTube category id.")
    tags: list[str] | None = Field(default=None, description="Optional video tags.")


class YouTubeUploaderTool(BaseTool):
    name: str = "youtube_data_api_uploader"
    description: str = (
        "Upload a local MP4 to YouTube using OAuth and the YouTube Data API. "
        "Use this as the final publishing step after fusion."
    )
    args_schema: Type[BaseModel] = YouTubeUploadInput

    @staticmethod
    def _load_env_file(env_file: Path) -> None:
        if not env_file.exists():
            return

        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

    @staticmethod
    def _build_credentials(client_secrets_path: Path, token_file_path: Path) -> Credentials:
        credentials: Credentials | None = None

        if token_file_path.exists():
            credentials = Credentials.from_authorized_user_file(str(token_file_path), SCOPES)

        if credentials and credentials.valid:
            return credentials

        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            if not client_secrets_path.exists():
                raise FileNotFoundError(
                    f"OAuth client secrets file not found: {client_secrets_path}. Download it from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_path), SCOPES)
            credentials = flow.run_local_server(port=0)

        token_file_path.parent.mkdir(parents=True, exist_ok=True)
        token_file_path.write_text(credentials.to_json(), encoding="utf-8")
        return credentials

    def _run(
        self,
        video_path: str,
        video_title: str,
        description: str = "",
        category_id: str = "22",
        tags: list[str] | None = None,
        env_file: str = ".env",
    ) -> str:
        self._load_env_file(Path(env_file))
        privacy = "private"
        made_for_kids = False
        client_secrets_path = os.getenv(
            "YOUTUBE_CLIENT_SECRETS",
            "/home/mm/dev/git/hackathon_spring_2026/client_secret_899706342462-esmuel8evro677rhffh1le2b5jl6cf7n.apps.googleusercontent.com.json",
        )
        token_file_path = os.getenv("YOUTUBE_TOKEN_FILE", "/home/mm/dev/git/hackathon_spring_2026/youtube_token.json")

        resolved_video_path = Path(video_path).expanduser()
        if not resolved_video_path.exists():
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Video file not found: {resolved_video_path}",
                },
                ensure_ascii=False,
            )

        try:
            credentials = self._build_credentials(
                Path(client_secrets_path).expanduser(),
                Path(token_file_path).expanduser(),
            )
            youtube = build("youtube", "v3", credentials=credentials)

            request_body = {
                "snippet": {
                    "title": video_title,
                    "description": description,
                    "categoryId": category_id,
                },
                "status": {
                    "privacyStatus": privacy,
                    "selfDeclaredMadeForKids": made_for_kids,
                },
            }
            if tags:
                request_body["snippet"]["tags"] = tags

            media = MediaFileUpload(str(resolved_video_path.resolve()), chunksize=1024 * 1024, resumable=True)
            request = youtube.videos().insert(part="snippet,status", body=request_body, media_body=media)

            response: dict | None = None
            while response is None:
                _, response = request.next_chunk()

            video_id = response.get("id") if response else None
            if not video_id:
                return json.dumps(
                    {
                        "status": "error",
                        "message": "YouTube API upload completed but no video id was returned.",
                    },
                    ensure_ascii=False,
                )

            return json.dumps(
                {
                    "status": "success",
                    "video_id": video_id,
                    "video_url": f"https://www.youtube.com/watch?v={video_id}",
                    "video_title": video_title,
                    "privacy": privacy,
                },
                ensure_ascii=False,
            )
        except FileNotFoundError as exc:
            return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False)
        except HttpError as exc:
            return json.dumps({"status": "error", "message": f"YouTube API error: {exc}"}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"Unexpected upload error: {exc}"}, ensure_ascii=False)
