from flask import Flask, request, jsonify, send_file
import time
import uuid
import os

app = Flask(__name__)

# Speichert die Jobs und ihren Start-Zeitpunkt (Timestamp)
active_jobs = {}
MOCK_DELAY_SECONDS = 2

@app.route('/upload/image', methods=['POST'])
def mock_upload():
    # Simuliert den erfolgreichen Upload
    return jsonify({"name": "mock_uploaded_image.jpg"})

@app.route('/queue', methods=['GET'])
def mock_queue():
    # Signalisiert dem Gatekeeper, dass das System leer und bereit ist
    return jsonify({"queue_running": [], "queue_pending": []})

@app.route('/prompt', methods=['POST'])
def mock_prompt():
    # Erzeugt eine Fake-Job-ID und merkt sich die aktuelle Zeit
    prompt_id = str(uuid.uuid4())
    active_jobs[prompt_id] = time.time()
    print(f"🛠️ MOCK: Job {prompt_id} empfangen. Starte 20-Sekunden-Timer...")
    return jsonify({"prompt_id": prompt_id})

@app.route('/history/<prompt_id>', methods=['GET'])
def mock_history(prompt_id):
    if prompt_id not in active_jobs:
        return jsonify({})

    elapsed_time = time.time() - active_jobs[prompt_id]
    
    if elapsed_time < MOCK_DELAY_SECONDS:
        # Job "rendert" noch
        return jsonify({})
    else:
        # 20 Sekunden sind um -> Erfolgs-JSON (inkl. Node 108 und images-Array)
        print(f"🛠️ MOCK: Timer abgelaufen für {prompt_id}. Sende Erfolg.")
        return jsonify({
            prompt_id: {
                "outputs": {
                    "108": {
                        "images": [
                            {
                                "filename": "mock_video.mp4",
                                "subfolder": "video",
                                "type": "output"
                            }
                        ]
                    }
                }
            }
        })

@app.route('/view', methods=['GET'])
def mock_view():
    # Liefert das simulierte Video zurück
    filename = request.args.get('filename', 'mock_video.mp4')
    
    # WICHTIG: MoviePy stürzt später ab, wenn die .mp4 beschädigt/leer ist.
    # Falls keine echte Datei da ist, erstellen wir zumindest einen Dummy.
    if not os.path.exists(filename):
        print("⚠️ Warnung: Keine echte 'mock_video.mp4' gefunden. Erstelle Dummy-Datei.")
        with open(filename, 'wb') as f:
            f.write(b'')
            
    return send_file(filename, as_attachment=True)

if __name__ == '__main__':
    print("🚀 Mock ComfyUI Server läuft auf http://127.0.0.1:8188")
    print("Tipp: Lege eine kleine, ECHTE Videodatei namens 'mock_video.mp4' in diesen Ordner,")
    print("damit deine spätere MoviePy-Pipeline beim Schneiden nicht mit einem Codec-Fehler abbricht.\n")
    app.run(host='0.0.0.0', port=8188)