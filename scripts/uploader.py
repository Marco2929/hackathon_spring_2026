"""Upload a video with the YouTube Data API v3.

Prerequisites:
1) pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2
2) Create OAuth client credentials in Google Cloud Console and download JSON credentials.
3) Enable the YouTube Data API v3 for your Google Cloud project.

Optional .env values:
- YOUTUBE_CLIENT_SECRETS
- YOUTUBE_TOKEN_FILE

Example:
python uploader.py --file video.mp4 --title "My Video" --description "From Python"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Upload videos with the YouTube Data API")
	parser.add_argument("--file", required=True, help="Path to the video file")
	parser.add_argument("--title", required=True, help="Video title")
	parser.add_argument("--description", default="", help="Video description")
	parser.add_argument(
		"--privacy",
		choices=["private", "public", "unlisted"],
		default="private",
		help="Video visibility",
	)
	parser.add_argument(
		"--made-for-kids",
		action="store_true",
		help="Mark video as made for kids",
	)
	parser.add_argument(
		"--client-secrets",
		default=None,
		help="Path to OAuth client secrets JSON",
	)
	parser.add_argument(
		"--token-file",
		default=None,
		help="Path to OAuth token cache JSON",
	)
	parser.add_argument(
		"--category-id",
		default="22",
		help="YouTube category id (default: 22 = People & Blogs)",
	)
	parser.add_argument(
		"--tags",
		nargs="*",
		default=None,
		help="Optional video tags, separated by spaces",
	)
	parser.add_argument(
		"--env-file",
		default=".env",
		help="Path to .env file that may contain uploader environment variables",
	)
	return parser.parse_args()


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
				f"OAuth client secrets file not found: {client_secrets_path}. "
				"Download it from Google Cloud Console."
			)
		flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_path), SCOPES)
		credentials = flow.run_local_server(port=0)

	token_file_path.parent.mkdir(parents=True, exist_ok=True)
	token_file_path.write_text(credentials.to_json(), encoding="utf-8")
	return credentials


def upload_video(
	video_path: Path,
	title: str,
	description: str,
	privacy: str,
	made_for_kids: bool,
	client_secrets_path: Path,
	token_file_path: Path,
	category_id: str,
	tags: list[str] | None,
) -> str:
	credentials = _build_credentials(client_secrets_path, token_file_path)
	youtube = build("youtube", "v3", credentials=credentials)

	request_body = {
		"snippet": {
			"title": title,
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

	media = MediaFileUpload(str(video_path.resolve()), chunksize=1024 * 1024, resumable=True)
	request = youtube.videos().insert(part="snippet,status", body=request_body, media_body=media)

	response: dict | None = None
	while response is None:
		_, response = request.next_chunk()

	video_id = response.get("id")
	if not video_id:
		raise RuntimeError("YouTube API upload completed but no video id was returned.")

	return f"https://www.youtube.com/watch?v={video_id}"


def main() -> int:
	args = parse_args()
	_load_env_file(Path(args.env_file))

	video_path = Path(args.file).expanduser()
	client_secrets_raw = args.client_secrets or os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secret_899706342462-esmuel8evro677rhffh1le2b5jl6cf7n.apps.googleusercontent.com.json")
	token_file_raw = args.token_file or os.getenv("YOUTUBE_TOKEN_FILE", "youtube_token.json")
	client_secrets_path = Path(client_secrets_raw).expanduser()
	token_file_path = Path(token_file_raw).expanduser()

	if not video_path.exists():
		print(f"Error: video file not found: {video_path}", file=sys.stderr)
		return 1

	try:
		video_url = upload_video(
			video_path=video_path,
			title=args.title,
			description=args.description,
			privacy=args.privacy,
			made_for_kids=args.made_for_kids,
			client_secrets_path=client_secrets_path,
			token_file_path=token_file_path,
			category_id=args.category_id,
			tags=args.tags,
		)
		print("Upload submitted successfully using the YouTube Data API.")
		print(f"Video URL: {video_url}")
		return 0
	except FileNotFoundError as exc:
		print(f"Error: {exc}", file=sys.stderr)
		return 1
	except HttpError as exc:
		print(f"YouTube API error: {exc}", file=sys.stderr)
		return 1
	except Exception as exc:
		print(f"Error: {exc}", file=sys.stderr)
		return 1


if __name__ == "__main__":
	raise SystemExit(main())
