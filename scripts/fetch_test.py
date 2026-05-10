import os
import sys
from pathlib import Path
import requests
from dotenv import load_dotenv

# 1. Umgebungsvariablen laden
load_dotenv()

def test_authenticated_download():
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("❌ Fehler: OPENROUTER_API_KEY nicht in den Umgebungsvariablen gefunden.")
        sys.exit(1)

    # Die exakte Ziel-URL aus deinem Beispiel
    target_url = "https://openrouter.ai/api/v1/videos/DjeCQIPiCYPoX78BuYcc/content?index=0"
    
    # Zielverzeichnis und Dateiname definieren
    output_dir = Path("output/test")
    output_dir.mkdir(parents=True, exist_ok=True)
    local_filename = output_dir / "fetched_video_test.mp4"

    # WICHTIG: Der Authorization-Header muss auch beim GET-Request für den Download mitgeliefert werden
    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    print(f"🔗 Starte authentifizierten Download von:\n   {target_url}")
    print("⏳ Verbinde mit Server...")

    try:
        # stream=True ist wichtig für den sicheren Download großer Binärdateien
        response = requests.get(target_url, headers=headers, stream=True, timeout=30)
        
        print(f"📥 HTTP Statuscode: {response.status_code}")

        # Prüfen, ob der Download genehmigt wurde (200 OK)
        if response.status_code == 200:
            print(f"💾 Schreibe Daten nach: {local_filename.resolve()} ...")
            
            # Binärdaten in Chunks auf die Festplatte schreiben
            with open(local_filename, "wb") as file_handle:
                for chunk in response.iter_content(chunk_size=8192):
                    file_handle.write(chunk)
                    
            print("\n🎉 --- DOWNLOAD ERFOLGREICH --- 🎉")
            print(f"🎬 Datei ist bereit und kann abgespielt werden!")
        
        elif response.status_code == 401:
            print("\n💥 --- FEHLER 401: UNAUTHORIZED --- 💥")
            print("Der Server hat den Zugriff verweigert. Typische Gründe:")
            print("1. Der API-Key ist ungültig oder abgelaufen.")
            print("2. Das Video gehört zu einem anderen API-Key / Account.")
            print("3. Die Video-URL ist abgelaufen (OpenRouter-Links haben oft eine begrenzte Gültigkeit).")
            try:
                print(f"Details: {response.json()}")
            except Exception:
                print(f"Details: {response.text}")
                
        else:
            print(f"\n💥 --- FEHLER BEIM DOWNLOAD --- 💥")
            print(f"Server antwortete mit unerwartetem Code: {response.status_code}")
            print(response.text[:500])

    except Exception as e:
        print(f"\n❌ Systemfehler beim Abrufen der URL:\n{str(e)}")

if __name__ == "__main__":
    test_authenticated_download()