from __future__ import annotations

import asyncio
import json
import re
import threading
from pathlib import Path
from typing import Type

import edge_tts
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class EdgeTTSInput(BaseModel):
    """Input schema for generating speech with Edge TTS."""

    text: str = Field(..., description="Text to convert to speech.")
    output_path: str = Field(
        default="output/tts/youtube_short.mp3",
        description="Path where the generated MP3 should be saved.",
    )
    voice: str = Field(default="de-DE-ConradNeural", description="Edge TTS voice short name.")
    rate: str = Field(default="+0%", description="Speech rate adjustment, e.g. +10%.")
    volume: str = Field(default="+0%", description="Speech volume adjustment, e.g. -10%.")


class EdgeTTSTool(BaseTool):
    name: str = "edge_tts_generate_audio"
    description: str = (
        "Convert text to an MP3 file using Edge TTS. "
        "Use this when a task needs a spoken narration output."
    )
    args_schema: Type[BaseModel] = EdgeTTSInput

    @staticmethod
    def _sanitize_text(text: str) -> str:
        # Remove bracketed stage directions such as [Visual], [Cut], [B-roll].
        without_brackets = re.sub(r"\[[^\]]*\]", " ", text)
        return re.sub(r"\s+", " ", without_brackets).strip()

    @staticmethod
    def _run_coro_safely(coro: object) -> None:
        """Run a coroutine in both normal and already-running-loop contexts."""
        try:
            asyncio.get_running_loop()
            loop_running = True
        except RuntimeError:
            loop_running = False

        if not loop_running:
            asyncio.run(coro)  # type: ignore[arg-type]
            return

        error: list[BaseException] = []

        def _target() -> None:
            try:
                asyncio.run(coro)  # type: ignore[arg-type]
            except BaseException as exc:  # pragma: no cover
                error.append(exc)

        thread = threading.Thread(target=_target, daemon=True)
        thread.start()
        thread.join()
        if error:
            raise error[0]

    @staticmethod
    def _normalize_percent(value: str) -> str:
        """Normalize percent inputs (e.g. 0%, 10, +5%) to Edge-TTS format."""
        raw = value.strip()
        match = re.fullmatch(r"([+-]?\d+)(%)?", raw)
        if not match:
            return raw
        number = int(match.group(1))
        sign = "+" if number >= 0 else ""
        return f"{sign}{number}%"

    @staticmethod
    def _normalize_hz(value: str) -> str:
        """Normalize pitch inputs (e.g. 0Hz, -20, +15hz) to Edge-TTS format."""
        raw = value.strip()
        match = re.fullmatch(r"([+-]?\d+)(hz)?", raw, flags=re.IGNORECASE)
        if not match:
            return raw
        number = int(match.group(1))
        sign = "+" if number >= 0 else ""
        return f"{sign}{number}Hz"

    def _run(
        self,
        text: str,
        output_path: str = "output/tts/youtube_short.mp3",
        voice: str = "en-US-AriaNeural",
        rate: str = "+0%",
        volume: str = "+0%",
    ) -> str:
        cleaned_text = self._sanitize_text(text)
        if not cleaned_text:
            return "TTS skipped: empty text input."

        normalized_rate = self._normalize_percent(rate)
        normalized_volume = self._normalize_percent(volume)
        normalized_pitch = "+0Hz"

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        async def _synthesize() -> None:
            communicate = edge_tts.Communicate(
                text=cleaned_text,
                voice=voice,
                rate=normalized_rate,
                volume=normalized_volume,
                pitch=normalized_pitch,
            )
            await communicate.save(str(out_path))

        self._run_coro_safely(_synthesize())
        payload = {
            "status": "success",
            "output_path": str(out_path),
            "resolved_output_path": str(out_path.resolve()),
            "voice": voice,
            "rate": normalized_rate,
            "volume": normalized_volume,
            "pitch": normalized_pitch,
            "char_count": len(cleaned_text),
            "cleaned_text_preview": cleaned_text[:240],
        }
        return json.dumps(payload, ensure_ascii=False)
