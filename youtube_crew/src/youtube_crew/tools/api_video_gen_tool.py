import base64
import io
import json
import os
import time
import requests
import urllib.request
from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from PIL import Image
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


class VideoInput(BaseModel):
    scene_descriptions: str = Field(
        ...,
        description="Semicolon-separated list of English prompts describing the generated shots."
    )
    image_paths: str = Field(
        ...,
                description="Semicolon-separated list of absolute image paths or filenames. For example 'output/scene_images/scene_01.png; output/scene_images/scene_02.png...'"
    )


class VideoTool(BaseTool):
    name: str = "video_generator"
    description: str = (
        "Generates a sequence of videos from images using OpenRouter's native video API (Kling/Veo). "
        "It handles the asynchronous rendering process and securely downloads the final MP4 files."
    )
    args_schema: Type[BaseModel] = VideoInput

    @staticmethod
    def _parse_semicolon_separated(text: str) -> list[str]:
        return [item.strip() for item in text.split(";") if item.strip()]

    def _run(self, scene_descriptions: str, image_paths: str) -> str:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return json.dumps({"status": "error", "message": "OPENROUTER_API_KEY not found in environment."})

        download_dir = Path("output/veo_videos")
        download_dir.mkdir(parents=True, exist_ok=True)

        scenes = self._parse_semicolon_separated(scene_descriptions)
        raw_image_paths = self._parse_semicolon_separated(image_paths)

        if not scenes or not raw_image_paths:
            return json.dumps({"status": "error", "message": "Missing scenes or image paths."})

        # Unified authorization headers required for POST, GET, and Downloading
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        results = []

        for idx, scene in enumerate(scenes):
            img_path_str = raw_image_paths[idx % len(raw_image_paths)]
            image_path = Path(img_path_str).expanduser()

            if not image_path.exists():
                results.append({"scene_index": idx + 1, "status": "error", "message": f"File not found: {image_path}"})
                continue

            try:
                # 1. Encode Raw Image (No Resizing)
                with open(image_path, "rb") as img_file:
                    b64_image = base64.b64encode(img_file.read()).decode('utf-8')

                # 2. Submit Generation Job
                payload = {
                    "model": "kwaivgi/kling-v3.0-std",
                    "prompt": scene,
                    "frame_images": [
                        {
                            "frame_type": "first_frame",
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}
                        }
                    ]
                }

                response = requests.post(
                    url="https://openrouter.ai/api/v1/videos",
                    headers=headers,
                    json=payload,
                    timeout=120
                )

                if response.status_code not in [200, 202]:
                    results.append({"scene_index": idx + 1, "status": "error", "message": f"API Error {response.status_code}: {response.text}"})
                    continue

                job_data = response.json()
                polling_url = job_data.get("polling_url")
                
                if polling_url and polling_url.startswith("/"):
                    polling_url = f"https://openrouter.ai{polling_url}"

                # 3. Wait for Rendering (Polling)
                final_video_url = None
                print(f"🎬 Processing scene {idx+1}... waiting for render.")
                
                while True:
                    # Explicitly pass headers to the polling GET request
                    poll_resp = requests.get(url=polling_url, headers=headers, timeout=15)
                    if poll_resp.status_code != 200:
                        time.sleep(5)
                        continue

                    status_data = poll_resp.json()
                    status = status_data.get("status")

                    if status == "completed":
                        urls = status_data.get("unsigned_urls", [])
                        if urls:
                            final_video_url = urls[0]
                        break
                    elif status in ["failed", "error"]:
                        results.append({"scene_index": idx + 1, "status": "error", "message": "Render failed on server."})
                        break
                    
                    time.sleep(10)
                
                if final_video_url:
                    print(f"\n🔗 [SCENE {idx + 1} RENDERED URL]: {final_video_url}\n")

                # 4. SECURE DOWNLOAD (Fixes the 401 Unauthorized Error)
                if final_video_url:
                    target_filename = f"scene_{idx + 1:02d}.mp4"
                    local_path = download_dir / target_filename
                    
                    # Use authenticated requests.get stream instead of unauthenticated urllib
                    print(f"⬇️ Downloading authenticated asset for scene {idx+1}...")
                    download_resp = requests.get(final_video_url, headers=headers, stream=True, timeout=60)
                    
                    if download_resp.status_code == 200:
                        with open(local_path, "wb") as f:
                            for chunk in download_resp.iter_content(chunk_size=8192):
                                f.write(chunk)
                                
                        results.append({
                            "scene_index": idx + 1,
                            "status": "success",
                            "local_video_path": str(local_path.resolve())
                        })
                    else:
                        results.append({
                            "scene_index": idx + 1, 
                            "status": "error", 
                            "message": f"Download rejected with status {download_resp.status_code}"
                        })

            except Exception as e:
                results.append({"scene_index": idx + 1, "status": "error", "message": str(e)})

        return json.dumps({
            "status": "completed", 
            "results": results
        }, ensure_ascii=False, indent=2)