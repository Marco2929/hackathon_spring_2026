from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
import requests


DEFAULT_OPENROUTER_IMAGE_MODEL = os.getenv(
    "OPENROUTER_IMAGE_MODEL",
    "black-forest-labs/flux.2-klein-4b",
)
DEFAULT_SCENE_IMAGE_OUTPUT_DIR = "output/scene_images"
DEFAULT_SCENE_IMAGE_SIZE = "500x500"
DEFAULT_OPENROUTER_CHAT_URL = os.getenv(
    "OPENROUTER_CHAT_URL",
    "https://openrouter.ai/api/v1/chat/completions",
)


class OpenRouterSceneImageInput(BaseModel):
    scene_descriptions: str = Field(
        ...,
        description=(
            "Semicolon-separated list of scene descriptions, e.g. 'Scene one...; Scene two...'."
        ),
    )
    image_paths: str = Field(
        ...,
        description=(
            "Semicolon-separated list of image paths, e.g. 'output/product_data/images/img1.jpg; output/product_data/images/img2.jpg'."
        ),
    )


class OpenRouterSceneImageTool(BaseTool):
    name: str = "openrouter_scene_image_generator"
    description: str = (
        "Generate scene images using OpenRouter FLUX from semicolon-separated scene descriptions and image paths."
    )
    args_schema: Type[BaseModel] = OpenRouterSceneImageInput

    @staticmethod
    def _parse_comma_separated(text: str) -> list[str]:
        return [item.strip() for item in text.split(";") if item.strip()]

    @staticmethod
    def _resolve_image_path(raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if candidate.exists():
            return candidate

        project_root = Path(__file__).resolve().parents[3]
        rooted = project_root / raw_path
        if rooted.exists():
            return rooted

        output_rooted = project_root / "output" / raw_path
        if output_rooted.exists():
            return output_rooted

        return candidate

    @staticmethod
    def _to_data_uri(image_path: Path) -> str:
        data = image_path.read_bytes()
        suffix = image_path.suffix.lower()
        if suffix == ".png":
            mime = "image/png"
        elif suffix == ".webp":
            mime = "image/webp"
        else:
            mime = "image/jpeg"
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    
    @staticmethod
    def _decode_image_data_url(image_url: str) -> bytes | None:
        if not image_url.startswith("data:"):
            return None
        try:
            _, b64_payload = image_url.split(",", 1)
            return base64.b64decode(b64_payload)
        except Exception:
            return None

    def _run(
        self,
        scene_descriptions: str,
        image_paths: str,
    ) -> str:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return json.dumps(
                {
                    "status": "error",
                    "message": "OPENROUTER_API_KEY is not set.",
                },
                ensure_ascii=False,
            )

        scenes = self._parse_comma_separated(scene_descriptions)
        if not scenes:
            return json.dumps(
                {
                    "status": "error",
                    "message": "No scene descriptions were found in scene_descriptions.",
                },
                ensure_ascii=False,
            )

        raw_image_paths = self._parse_comma_separated(image_paths)
        if not raw_image_paths:
            return json.dumps(
                {
                    "status": "error",
                    "message": "No image paths were found in image_paths.",
                },
                ensure_ascii=False,
            )

        output_path = Path(DEFAULT_SCENE_IMAGE_OUTPUT_DIR).expanduser()
        output_path.mkdir(parents=True, exist_ok=True)

        generated: list[dict[str, str]] = []
        for idx, scene in enumerate(scenes, start=1):
            selected_raw = raw_image_paths[(idx - 1) % len(raw_image_paths)]
            selected_path = self._resolve_image_path(selected_raw)
            if not selected_path.exists():
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"Reference image not found: {selected_raw}",
                    },
                    ensure_ascii=False,
                )

            image_data_uri = self._to_data_uri(selected_path)

            payload = {
                "model": DEFAULT_OPENROUTER_IMAGE_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": scene,
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_data_uri,
                                },
                            },
                        ],
                    }
                ],
                "modalities": ["image"],
            }

            try:
                response = requests.post(
                    url=DEFAULT_OPENROUTER_CHAT_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    data=json.dumps(payload),
                    timeout=60,
                )
                response.raise_for_status()
                body = response.json()
            except Exception as exc:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"OpenRouter request failed: {exc}",
                        "scene_index": idx,
                    },
                    ensure_ascii=False,
                )

            choices = body.get("choices") if isinstance(body, dict) else None
            if not isinstance(choices, list) or not choices:
                return json.dumps(
                    {
                        "status": "error",
                        "message": "OpenRouter returned no choices.",
                        "scene_index": idx,
                        "raw_response": body,
                    },
                    ensure_ascii=False,
                )

            first_choice = choices[0] if isinstance(choices[0], dict) else {}
            message = first_choice.get("message") if isinstance(first_choice, dict) else None
            images = message.get("images") if isinstance(message, dict) else None
            if not isinstance(images, list) or not images:
                return json.dumps(
                    {
                        "status": "error",
                        "message": "OpenRouter response did not include message.images.",
                        "scene_index": idx,
                        "raw_response": body,
                    },
                    ensure_ascii=False,
                )

            first_image = images[0] if isinstance(images[0], dict) else {}
            image_url_obj = first_image.get("image_url") if isinstance(first_image, dict) else None
            image_url = image_url_obj.get("url") if isinstance(image_url_obj, dict) else None
            if not isinstance(image_url, str) or not image_url:
                return json.dumps(
                    {
                        "status": "error",
                        "message": "OpenRouter image object did not include image_url.url.",
                        "scene_index": idx,
                        "raw_response": body,
                    },
                    ensure_ascii=False,
                )

            image_bytes = self._decode_image_data_url(image_url)
            if image_bytes is None:
                try:
                    image_response = requests.get(image_url, timeout=60)
                    image_response.raise_for_status()
                    image_bytes = image_response.content
                except Exception as exc:
                    return json.dumps(
                        {
                            "status": "error",
                            "message": f"Failed to download generated image: {exc}",
                            "scene_index": idx,
                            "raw_response": body,
                        },
                        ensure_ascii=False,
                    )

            scene_filename = f"scene_{idx:02d}.png"
            scene_file = output_path / scene_filename
            scene_file.write_bytes(image_bytes)

            generated.append(
                {
                    "scene_index": str(idx),
                    "scene_description": scene,
                    "reference_image": str(selected_path),
                    "generated_image": str(scene_file),
                }
            )

        return json.dumps(
            {
                "status": "success",
                "model": DEFAULT_OPENROUTER_IMAGE_MODEL,
                "output_dir": str(output_path),
                "generated_images": generated,
            },
            ensure_ascii=False,
        )