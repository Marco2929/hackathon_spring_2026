import urllib.request
import urllib.error
import urllib.parse
import json
import os
import time

PC_IP = "192.168.178.128"
DOWNLOAD_DIR = "./output" 

def upload_image_to_comfyui(image_path):
    url = f"http://{PC_IP}:8188/upload/image"
    with open(image_path, "rb") as f:
        image_data = f.read()

    filename = os.path.basename(image_path)
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"image\"; filename=\"{filename}\"\r\n"
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode('utf-8') + image_data + f"\r\n--{boundary}--\r\n".encode('utf-8')

    req = urllib.request.Request(url, data=body)
    req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
    
    try:
        response = urllib.request.urlopen(req)
        result = json.loads(response.read())
        print(f"✅ Bild hochgeladen als: {result['name']}")
        return result['name']
    except Exception as e:
        print(f"❌ Fehler beim Bilder-Upload: {e}")
        return None

def is_queue_empty():
    queue_url = f"http://{PC_IP}:8188/queue"
    try:
        req = urllib.request.Request(queue_url)
        response = urllib.request.urlopen(req)
        queue_data = json.loads(response.read())
        running = len(queue_data.get("queue_running", []))
        pending = len(queue_data.get("queue_pending", []))
        return running == 0 and pending == 0
    except Exception as e:
        return False

def wait_for_empty_queue():
    print("🔍 Prüfe Systemauslastung auf dem PC...")
    while not is_queue_empty():
        print("⏳ PC ist noch beschäftigt. Warte 10 Sekunden...")
        time.sleep(10)
    print("✅ PC ist bereit. Starte neuen Job.")

def download_generated_file(filename, subfolder, folder_type):
    """Lädt die fertige Datei vom PC auf den Laptop herunter."""
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    # URL-Parameter kodieren (falls Leerzeichen im Dateinamen sind)
    params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    query_string = urllib.parse.urlencode(params)
    download_url = f"http://{PC_IP}:8188/view?{query_string}"
    
    local_save_path = os.path.join(DOWNLOAD_DIR, filename)
    
    print(f"⬇️ Lade Datei herunter: {filename}...")
    try:
        urllib.request.urlretrieve(download_url, local_save_path)
        print(f"🎉 Datei erfolgreich gespeichert: {local_save_path}")
        return local_save_path
    except Exception as e:
        print(f"❌ Fehler beim Download: {e}")
        return None

def wait_for_job_completion(prompt_id):
    history_url = f"http://{PC_IP}:8188/history/{prompt_id}"
    print(f"⏳ Warte auf Video-Rendering (GPU arbeitet)... Job-ID: {prompt_id}")
    
    while True:
        try:
            req = urllib.request.Request(history_url)
            response = urllib.request.urlopen(req)
            history_data = json.loads(response.read())
            
            if prompt_id in history_data:
                print("✅ Render-Job erfolgreich abgeschlossen!")
                
                outputs = history_data[prompt_id].get("outputs", {})
                
                for node_id, node_output in outputs.items():
                    for media_key in ["videos", "images", "gifs"]:
                        if media_key in node_output:
                            for item in node_output[media_key]:
                                if item.get("filename", "").endswith(".mp4"):
                                    return item
                
                return None
                
            time.sleep(5)
        except Exception as e:
            print(f"⚠️ Warnung beim Status-Check: {e}")
            time.sleep(5)

def generate_video(prompt_text, local_image_path):
    wait_for_empty_queue()

    uploaded_filename = upload_image_to_comfyui(local_image_path)
    if not uploaded_filename:
        return None

    try:
        with open("/home/mm/dev/git/hackathon_spring_2026/YouTube_gen_smol.json", "r", encoding="utf-8") as f:
            workflow = json.load(f)
    except FileNotFoundError:
        print("❌ Abbruch: Datei 'YouTube_gen_smol.json' nicht gefunden.")
        return None

    try:
        workflow["6"]["inputs"]["text"] = prompt_text
        workflow["56"]["inputs"]["image"] = uploaded_filename
    except KeyError as e:
        print(f"❌ Abbruch: Node-ID {e} nicht gefunden. Hast du die JSON nach dem Aktivieren des Bildes (Strg+B) gespeichert?")
        return None

    payload = {"prompt": workflow}
    data = json.dumps(payload).encode('utf-8')
    url = f"http://{PC_IP}:8188/prompt"
    
    req = urllib.request.Request(url, data=data)
    
    req.add_header('Content-Type', 'application/json')
    req.add_header('Accept', 'application/json')
    
    try:
        response = urllib.request.urlopen(req)
        result = json.loads(response.read())
        prompt_id = result['prompt_id']
        print(f"✅ Video-Job in Warteschlange eingereiht! Prompt_ID: {prompt_id}")
        
        video_metadata = wait_for_job_completion(prompt_id)
        
        if video_metadata:
            # Download auslösen
            final_path = download_generated_file(
                video_metadata["filename"], 
                video_metadata["subfolder"], 
                video_metadata["type"]
            )
            return final_path
        else:
            print("❌ Kein Video-Output in der History gefunden.")
            return None
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"\n🚨 KRITISCHER API-FEHLER: HTTP {e.code} - {error_body}\n")
        return None
    except Exception as e:
        print(f"❌ Fehler beim API-Aufruf: {e}")
        return None

if __name__ == "__main__":
    mein_test_prompt = "Cinematic macro shot, extremely slow and smooth forward zoom on a sleek modern tablet floating weightlessly in deep outer space. The tablet slowly rotates by 5 degrees. The screen is pure black, reflecting a breathtaking galaxy with purple and blue nebulae. Soft cosmic rim lighting on the metallic edges of the device. 4k resolution, photorealistic, sharp focus, masterpiece."
    mein_bild_pfad = "/home/mm/dev/git/hackathon_spring_2026/output/B0DJWBDNCW/images/product_image_01.jpg"
    
    if os.path.exists(mein_bild_pfad):
        generate_video(mein_test_prompt, mein_bild_pfad)
    else:
        print(f"Fehler: Bild unter '{mein_bild_pfad}' existiert nicht.")