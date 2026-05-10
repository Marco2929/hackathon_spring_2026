import base64
import io
import json
import os
import time
from dotenv import load_dotenv
from PIL import Image
import requests

load_dotenv()

def generate_video_from_image():
    # 1. API-Key laden
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return "❌ Fehler: OPENROUTER_API_KEY nicht in den Umgebungsvariablen gefunden."

    image_path = "/home/mm/dev/git/hackathon_spring_2026/youtube_crew/output/scene_images/scene_04.png"
    prompt_text = "Subtle cinematic motion, camera pans slowly to the right, soft lighting changes."

    print(f"🔍 Lade und kodiere Startbild: {image_path}")

    # 2. Bild vorbereiten (RGB, sichere Auflösung für Kling/Veo)
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            # Kling und Veo arbeiten am stabilsten mit exakten 9:16 Werten
            img_resized = img.resize((720, 1280), Image.Resampling.LANCZOS)
            
            buffer = io.BytesIO()
            img_resized.save(buffer, format="JPEG", quality=95)
            b64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception as e:
        return f"❌ Fehler beim Verarbeiten des lokalen Bildes: {str(e)}"

    # 3. Schritt 1: Video-Generierungsauftrag absenden (POST)
    print("🚀 Sende Request an OpenRouter native Video-API...")
    
    # Hier nutzen wir exakt das Schema für Image-to-Video auf OpenRouter
    payload = {
        "model": "kwaivgi/kling-v3.0-std",  # Funktioniert auch mit "google/veo-3.1-fast"
        "prompt": prompt_text,
        "frame_images": [
            {
                "frame_type": "first_frame",
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64_image}"
                }
            }
        ]
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        url="https://openrouter.ai/api/v1/videos",
        headers=headers,
        data=json.dumps(payload),
        timeout=15  # <-- Verhindert unendliches Aufhängen
    )

    # Erlaube sowohl 200 (OK) als auch 202 (Accepted)
    if response.status_code not in [200, 202]:
        return f"💥 API Fehler beim Starten des Jobs (Code {response.status_code}): {response.text}"
    
    result = response.json()
    job_id = result.get("id")
    polling_url = result.get("polling_url")
    
    if not job_id or not polling_url:
        return f"❌ Unerwartete API-Antwort (keine Job-ID oder Polling-URL): {result}"

    print(f"✅ Auftrag erfolgreich platziert! Job-ID: {job_id}")

    # OpenRouter liefert manchmal relative Polling-URLs zurück
    if polling_url.startswith("/"):
        polling_url = f"https://openrouter.ai{polling_url}"

    # 4. Schritt 2: Polling auf Fertigstellung (GET)
    print(f"⏳ Warte auf Rendering des Videos... (Polling alle 5 Sekunden)")
    
    while True:
        poll_response = requests.get(
            url=polling_url,
            headers={"Authorization": f"Bearer {api_key}"}
        )
        
        if poll_response.status_code != 200:
            print(f"⚠️ Polling-Fehler (Code {poll_response.status_code}), versuche es weiter...")
            time.sleep(5)
            continue
            
        status_data = poll_response.json()
        current_status = status_data.get("status")
        print(f"🔄 Status: {current_status}")

        if current_status == "completed":
            urls = status_data.get("unsigned_urls", [])
            if urls:
                final_video_url = urls[0]
                print(f"\n🎉 --- VIDEO ERFOLGREICH GENERIERT --- 🎉")
                print(f"🔗 URL: {final_video_url}")
                return final_video_url
            else:
                return f"❌ Video abgeschlossen, aber keine Download-URL gefunden: {status_data}"
                
        elif current_status == "failed":
            error_msg = status_data.get("error", "Unbekannter Fehler")
            return f"💥 Rendering auf den Servern fehlgeschlagen: {error_msg}"

        time.sleep(5)

if __name__ == "__main__":
    ergebnis = generate_video_from_image()
    print("\n--- SKRIPT-ERGEBNIS ---")
    print(ergebnis)