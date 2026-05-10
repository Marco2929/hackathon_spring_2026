import base64
import os
from crewai.tools import BaseTool
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class MultiImageDescriptionTool(BaseTool):
    name: str = "multi_image_description_tool"
    description: str = (
        "Analysiert eine Liste von Bildpfaden. Input muss ein String von Pfaden sein, "
        "getrennt durch Kommas (z.B. 'pfad1.jpg, pfad2.jpg')."
    )

    def _run(self, image_paths: str) -> str:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )
        

        paths = [p.strip() for p in image_paths.split(",")]
        results = []
        
        for path in paths:
            if not path: continue
            try:
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode('utf-8')
                
                response = client.chat.completions.create(
                    model="google/gemini-2.5-flash",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Describe this product image concisely. Focus on materials and style."},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                        ]
                    }]
                )
                results.append(f"Image ({path}): {response.choices[0].message.content}")
            except Exception as e:
                results.append(f"Image ({path}): Error - {str(e)}")
        
        return "\n".join(results)