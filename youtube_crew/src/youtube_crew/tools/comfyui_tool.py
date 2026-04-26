from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

DEFAULT_COMFYUI_HOST = os.getenv("COMFYUI_HOST", "192.168.178.128")
DEFAULT_COMFYUI_PROMPT_URL = os.getenv("COMFYUI_PROMPT_URL", f"http://{DEFAULT_COMFYUI_HOST}:8188/prompt")
DEFAULT_WORKFLOW_PATH = Path(os.getenv("COMFYUI_WORKFLOW_PATH", "/home/mm/dev/git/hackathon_spring_2026/YouTube_gen_smol.json"))
DEFAULT_DOWNLOAD_DIR = Path(os.getenv("COMFYUI_DOWNLOAD_DIR", "/home/mm/dev/git/hackathon_spring_2026/youtube_crew/output/comfyui"))
DEFAULT_SAVE_NODE_ID = os.getenv("COMFYUI_SAVE_NODE_ID", "58")


class ComfyUIVideoInput(BaseModel):
    scene_descriptions: str = Field(
        ..., 
        description="Semicolon-separated list of English prompts describing the generated shots."
    )
    image_paths: str = Field(
        ...,
        description="Semicolon-separated list of absolute image paths or filenames. For example 'output/scene_images/scene_image_01.jpg; output/scene_images/scene_image_02.jpg...'"
    )


def upload_image_to_comfyui(host: str, image_path: Path) -> str | None:
    url = f"http://{host}:8188/upload/image"
    with image_path.open("rb") as file_handle:
        image_data = file_handle.read()

    filename = image_path.name
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"image\"; filename=\"{filename}\"\r\n"
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode("utf-8") + image_data + f"\r\n--{boundary}--\r\n".encode("utf-8")

    request = urllib.request.Request(url, data=body)
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    try:
        response = urllib.request.urlopen(request, timeout=10)
        result = json.loads(response.read())
        print(f"✅ Bild hochgeladen als: {result['name']}")
        return result["name"]
    except Exception as exc:
        print(f"❌ Fehler beim Bilder-Upload: {exc}")
        return None


def is_queue_empty(host: str) -> bool:
    queue_url = f"http://{host}:8188/queue"
    try:
        request = urllib.request.Request(queue_url)
        response = urllib.request.urlopen(request, timeout=5)
        queue_data = json.loads(response.read())
        running = len(queue_data.get("queue_running", []))
        pending = len(queue_data.get("queue_pending", []))
        return running == 0 and pending == 0
    except Exception:
        return False


def wait_for_empty_queue(host: str) -> None:
    print("🔍 Prüfe Systemauslastung auf dem PC...")
    while not is_queue_empty(host):
        print("⏳ PC ist noch beschäftigt. Warte 10 Sekunden...")
        time.sleep(10)
    print("✅ PC ist bereit. Starte neuen Job.")


def download_generated_file(host: str, filename: str, subfolder: str, folder_type: str, download_dir: Path, target_filename: str | None = None) -> str | None:
    download_dir.mkdir(parents=True, exist_ok=True)

    params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    query_string = urllib.parse.urlencode(params)
    download_url = f"http://{host}:8188/view?{query_string}"

    save_name = target_filename if target_filename else filename
    local_save_path = download_dir / save_name

    print(f"⬇️ Lade Datei herunter: {filename} -> {save_name}...")
    try:
        urllib.request.urlretrieve(download_url, str(local_save_path))
        print(f"🎉 Datei erfolgreich gespeichert: {local_save_path}")
        return str(local_save_path)
    except Exception as exc:
        print(f"❌ Fehler beim Download: {exc}")
        return None


def wait_for_job_completion(host: str, prompt_id: str, save_node_id: str | None = None) -> dict | None:
    history_url = f"http://{host}:8188/history/{prompt_id}"
    print(f"⏳ Warte auf Video-Rendering... Job-ID: {prompt_id}")

    while True:
        try:
            request = urllib.request.Request(history_url)
            response = urllib.request.urlopen(request)
            history_data = json.loads(response.read())

            if prompt_id in history_data:
                print("✅ Render-Job erfolgreich abgeschlossen!")
                outputs = history_data[prompt_id].get("outputs", {})

                for node_id, node_output in outputs.items():
                    for media_key in ["videos", "images", "gifs"]:
                        if media_key in node_output:
                            for item in node_output[media_key]:
                                if item.get("filename", "").endswith(".mp4"):
                                    print(f"🎬 Korrektes finales Video identifiziert: {item.get('filename')}")
                                    return item

                if save_node_id:
                    print(f"❌ Fehler: Der angegebene Save-Node ({save_node_id}) hat keinen Output produziert.")
                return None

            time.sleep(5)
        except Exception:
            time.sleep(5)


class ComfyUIVideoTool(BaseTool):
    name: str = "ComfyUI Batch Video Generator"
    description: str = (
        "Generate a sequence of videos from a semicolon-separated list of source images and prompts "
        "via a local ComfyUI instance. Processes frame by frame."
    )
    args_schema: Type[BaseModel] = ComfyUIVideoInput

    @staticmethod
    def _parse_semicolon_separated(text: str) -> list[str]:
        return [item.strip() for item in text.split(";") if item.strip()]

    def _run(
        self,
        scene_descriptions: str,
        image_paths: str,
    ) -> str:
        host = DEFAULT_COMFYUI_HOST
        prompt_url = DEFAULT_COMFYUI_PROMPT_URL
        workflow_file = DEFAULT_WORKFLOW_PATH
        download_dir = DEFAULT_DOWNLOAD_DIR
        save_node_id = DEFAULT_SAVE_NODE_ID

        scenes = self._parse_semicolon_separated(scene_descriptions)
        raw_image_paths = self._parse_semicolon_separated(image_paths)

        if not scenes:
            return json.dumps(
                {
                    "status": "error", 
                    "message": "No scene descriptions provided."
                }, 
                ensure_ascii=False
            )
        
        if not raw_image_paths:
            return json.dumps(
                {
                    "status": "error", 
                    "message": "No image paths provided."
                }, 
                ensure_ascii=False
            )

        try:
            with workflow_file.open("r", encoding="utf-8") as file_handle:
                base_workflow = json.load(file_handle)
        except FileNotFoundError:
            return json.dumps(
                {
                    "status": "error", 
                    "message": f"Workflow file '{workflow_file}' not found."
                }, 
                ensure_ascii=False
            )

        generated: list[dict[str, str]] = []

        for idx, scene in enumerate(scenes, start=1):
            selected_raw = raw_image_paths[(idx - 1) % len(raw_image_paths)]
            
            print(f"\n--- Verarbeite Szene {idx}/{len(scenes)} ---")

            wait_for_empty_queue(host)

            resolved_image_path = Path(selected_raw).expanduser()

            if not resolved_image_path.exists():
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"Reference image not found: {selected_raw}",
                        "scene_index": idx,
                    },
                    ensure_ascii=False,
                )

            uploaded_filename = upload_image_to_comfyui(host, resolved_image_path)
            if not uploaded_filename:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"Upload failed for image: {resolved_image_path}",
                        "scene_index": idx,
                    },
                    ensure_ascii=False,
                )

            workflow = json.loads(json.dumps(base_workflow))
            try:
                workflow["6"]["inputs"]["text"] = scene
                workflow["56"]["inputs"]["image"] = uploaded_filename
            except KeyError as exc:
                return json.dumps(
                    {
                        "status": "error", 
                        "message": f"Node-ID {exc} missing in '{workflow_file}'.",
                        "scene_index": idx,
                    }, 
                    ensure_ascii=False
                )

            payload = {"prompt": workflow}
            data = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(prompt_url, data=data)

            try:
                response = urllib.request.urlopen(request, timeout=10)
                result = json.loads(response.read())
                prompt_id = result["prompt_id"]

                video_metadata = wait_for_job_completion(host, prompt_id, save_node_id)

                if not video_metadata:
                    return json.dumps(
                        {
                            "status": "error",
                            "message": "No video output found in history.",
                            "scene_index": idx,
                        },
                        ensure_ascii=False,
                    )

                original_extension = Path(video_metadata["filename"]).suffix
                target_filename = f"{idx:02d}_scene{original_extension}"

                final_path = download_generated_file(
                    host,
                    video_metadata["filename"],
                    video_metadata["subfolder"],
                    video_metadata["type"],
                    download_dir,
                    target_filename=target_filename
                )

                if not final_path:
                    return json.dumps(
                        {
                            "status": "error",
                            "message": "Video download failed.",
                            "scene_index": idx,
                        },
                        ensure_ascii=False,
                    )

                generated.append({
                    "scene_index": str(idx),
                    "scene_description": scene,
                    "reference_image": str(resolved_image_path),
                    "generated_video": final_path,
                })

            except Exception as exc:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"API request failed: {exc}",
                        "scene_index": idx,
                    },
                    ensure_ascii=False,
                )

        return json.dumps(
            {
                "status": "success",
                "output_dir": str(download_dir),
                "generated_videos": generated,
            },
            ensure_ascii=False,
        )