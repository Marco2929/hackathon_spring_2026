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
# 192.168.178.128
DEFAULT_COMFYUI_HOST = os.getenv("COMFYUI_HOST", "127.0.0.1")
DEFAULT_COMFYUI_PROMPT_URL = os.getenv("COMFYUI_PROMPT_URL", f"http://{DEFAULT_COMFYUI_HOST}:8188/prompt")
DEFAULT_WORKFLOW_PATH = Path(os.getenv("COMFYUI_WORKFLOW_PATH", "/home/mm/dev/git/hackathon_spring_2026/YouTube_gen_smol.json"))
DEFAULT_IMAGE_DIR = Path(
    os.getenv(
        "COMFYUI_IMAGE_DIR",
        "output/product_data/images/",
    )
)
DEFAULT_DOWNLOAD_DIR = Path(os.getenv("COMFYUI_DOWNLOAD_DIR", "/home/mm/dev/git/hackathon_spring_2026/youtube_crew/output/comfyui"))
DEFAULT_SAVE_NODE_ID = os.getenv("COMFYUI_SAVE_NODE_ID", "58")


class ComfyUIVideoInput(BaseModel):
    prompt_text: str = Field(..., description="English prompt describing the generated shot.")
    image_path: str = Field(
        ...,
        description="Absolute image path or filename relative to the configured image directory.",
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


def download_generated_file(host: str, filename: str, subfolder: str, folder_type: str, download_dir: Path) -> str | None:
    """Lädt die fertige Datei vom PC auf den lokalen Rechner herunter."""
    download_dir.mkdir(parents=True, exist_ok=True)

    params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    query_string = urllib.parse.urlencode(params)
    download_url = f"http://{host}:8188/view?{query_string}"

    local_save_path = download_dir / filename

    print(f"⬇️ Lade Datei herunter: {filename}...")
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

                # Like comfy_test.py: search every node and return the first .mp4 output we find.
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
    name: str = "ComfyUI Video Generator"
    description: str = (
        "Generate a video from a source image and prompt via a local ComfyUI instance. "
        "Use this for the final technical rendering step."
    )
    args_schema: Type[BaseModel] = ComfyUIVideoInput

    def _run(
        self,
        prompt_text: str,
        image_path: str,
    ) -> str:
        host = DEFAULT_COMFYUI_HOST
        prompt_url = DEFAULT_COMFYUI_PROMPT_URL
        workflow_file = DEFAULT_WORKFLOW_PATH
        download_dir = DEFAULT_DOWNLOAD_DIR
        save_node_id = DEFAULT_SAVE_NODE_ID

        wait_for_empty_queue(host)

        candidate_path = Path(image_path).expanduser()
        if candidate_path.is_absolute() or candidate_path.exists():
            resolved_image_path = candidate_path
        else:
            resolved_image_path = DEFAULT_IMAGE_DIR / candidate_path

        if not resolved_image_path.exists():
            return f"Fehler: Bild nicht gefunden: {resolved_image_path}"

        uploaded_filename = upload_image_to_comfyui(host, resolved_image_path)
        if not uploaded_filename:
            return "Fehler: Bild konnte nicht hochgeladen werden."

        try:
            with workflow_file.open("r", encoding="utf-8") as file_handle:
                workflow = json.load(file_handle)
        except FileNotFoundError:
            return f"Fehler: Datei '{workflow_file}' nicht gefunden."

        try:
            # 1. Den englischen Video-Prompt in Node 6 pumpen
            workflow["6"]["inputs"]["text"] = prompt_text
            # 2. Den Dateinamen des hochgeladenen Bildes in Node 56 pumpen
            workflow["56"]["inputs"]["image"] = uploaded_filename
        except KeyError as exc:
            return f"Fehler: Node-ID {exc} in '{workflow_file}' nicht gefunden."

        payload = {"prompt": workflow}
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(prompt_url, data=data)

        try:
            response = urllib.request.urlopen(request, timeout=10)
            result = json.loads(response.read())
            prompt_id = result["prompt_id"]

            video_metadata = wait_for_job_completion(host, prompt_id, save_node_id)

            if not video_metadata:
                return "Fehler: Kein Video-Output in der History gefunden."

            final_path = download_generated_file(
                host,
                video_metadata["filename"],
                video_metadata["subfolder"],
                video_metadata["type"],
                download_dir,
            )
            if not final_path:
                return "Fehler: Video konnte nicht heruntergeladen werden."

            payload = {
                "status": "success",
                "video_path": final_path,
                "prompt_id": prompt_id,
            }
            return json.dumps(payload, ensure_ascii=False)
        except Exception as exc:
            return f"Systemfehler beim API-Aufruf: {exc}"