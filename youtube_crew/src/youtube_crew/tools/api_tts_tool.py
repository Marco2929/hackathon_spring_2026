import os
import re
from pathlib import Path
from crewai.tools import BaseTool
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class TTSTool(BaseTool):
    name: str = "openai_tts_generate_audio"
    description: str = (
        "Convert text to an MP3 file using the GPT-4o-Mini TTS model. "
        "Input MUST be a single string containing the text to convert to speech."
    )

    def _sanitize_text(self, text: str) -> str:
        """Removes stage directions like [Visual] or [Cut] and normalizes spaces."""
        without_brackets = re.sub(r"\[[^\]]*\]", " ", text)
        return re.sub(r"\s+", " ", without_brackets).strip()

    def _run(self, text: str) -> str:
        cleaned_text = self._sanitize_text(text)
        if not cleaned_text:
            return "TTS skipped: empty text input."

        # Initialize the OpenAI client (using OpenRouter routing if configured in your environment)
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",  # Adjust if you use the standard OpenAI endpoint
            api_key=os.getenv("OPENROUTER_API_KEY"),  # Fallback to OPENAI_API_KEY if needed
        )

        # Define and ensure the output directory exists
        output_path = Path("output/tts/youtube_short.mp3")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # The standard OpenAI SDK method for TTS
            response = client.audio.speech.create(
                model="openai/gpt-4o-mini-tts-2025-12-15",
                voice="fable",
                input=cleaned_text,
                response_format="mp3"
            )
            
            # Save the binary response to the MP3 file
            response.stream_to_file(output_path)
            
            return f"Success: Audio successfully generated and saved to {output_path.resolve()}"
            
        except Exception as e:
            return f"Error generating audio: {str(e)}"