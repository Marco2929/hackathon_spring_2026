import base64
import os
import sys
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# --- CONFIGURATION & ENVIRONMENT ---
# Load the .env file from the current directory
load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")

if not api_key:
    print("Error: OPENROUTER_API_KEY not found in .env file or environment.")
    sys.exit(1)

# Initialize OpenRouter Client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
)

# File Paths
image_path = "/home/mm/dev/git/hackathon_spring_2026/product_image_01.jpg"
model_id = "google/gemini-2.0-flash-lite-001"

# --- HELPER FUNCTIONS ---
def encode_image(path):
    """Converts a local image file to a base64 string."""
    try:
        with open(path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except FileNotFoundError:
        print(f"Error: The image file was not found at {path}")
        sys.exit(1)

# --- MAIN EXECUTION ---
def run_analysis():
    print(f"Loading image: {image_path}", flush=True)
    base64_image = encode_image(image_path)

    print(f"Sending request to OpenRouter...", flush=True)

    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Provide a concise, 2-3 sentence description of this image. Focus only on the facts."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ]
        )

        answer = response.choices[0].message.content
        print(f"\nErgebnis:\n{answer}")

    except Exception as e:
        print(f"\nAPI Error: {e}")

if __name__ == "__main__":
    run_analysis()