import urllib.request
import urllib.parse
import os

PC_IP = "192.168.178.128"
DOWNLOAD_DIR = "./output_videos"

def get_my_video():
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
        
    filename = "Wan2.2_i2v_00004_.mp4"
    subfolder = "video"
    folder_type = "output"
    
    params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    query_string = urllib.parse.urlencode(params)
    download_url = f"http://{PC_IP}:8188/view?{query_string}"
    
    local_save_path = os.path.join(DOWNLOAD_DIR, filename)
    print(f"⬇️ Lade {filename} herunter...")
    
    try:
        urllib.request.urlretrieve(download_url, local_save_path)
        print(f"🎉 Erfolg! Schau in den Ordner: {local_save_path}")
    except Exception as e:
        print(f"❌ Fehler: {e}")

if __name__ == "__main__":
    get_my_video()