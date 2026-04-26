from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class VideoFusionInput(BaseModel):
    clips_text: str = Field(
        ...,
        description="Text that contains generated clip paths (usually output from generate_video_clips_task).",
    )
    audio_path: str = Field(
        default="output/tts/youtube_short.mp3",
        description="Path to the generated narration audio file.",
    )
    output_path: str = Field(
        default="output/final/youtube_short_final.mp4",
        description="Output MP4 path for the fused final video.",
    )


class VideoFusionTool(BaseTool):
    name: str = "video_fusion_tool"
    description: str = (
        "Fuse multiple generated video clips with the narration audio into one final MP4 file "
        "using ffmpeg concatenation and muxing."
    )
    args_schema: Type[BaseModel] = VideoFusionInput

    @staticmethod
    def _extract_clip_paths(clips_text: str) -> list[Path]:
        candidates = re.findall(r"(?:[A-Za-z]:\\[^\s\"']+\.mp4|/[^\s\"']+\.mp4|[^\s\"']+\.mp4)", clips_text)
        seen: set[str] = set()
        resolved: list[Path] = []
        for raw in candidates:
            normalized = raw.strip().strip('"').strip("'").rstrip(",.;")
            if normalized in seen:
                continue
            seen.add(normalized)
            resolved.append(Path(normalized).expanduser())
        return resolved

    @staticmethod
    def _run_command(command: list[str]) -> tuple[int, str]:
        process = subprocess.run(command, capture_output=True, text=True)
        stderr = process.stderr.strip() if process.stderr else ""
        return process.returncode, stderr

    @staticmethod
    def _probe_duration_seconds(file_path: Path) -> float | None:
        command = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ]
        process = subprocess.run(command, capture_output=True, text=True)
        if process.returncode != 0:
            return None
        raw = (process.stdout or "").strip()
        try:
            value = float(raw)
            return value if value > 0 else None
        except ValueError:
            return None

    def _run(self, clips_text: str, audio_path: str = "output/tts/youtube_short.mp3", output_path: str = "output/final/youtube_short_final.mp4") -> str:
        if shutil.which("ffmpeg") is None:
            return json.dumps(
                {
                    "status": "error",
                    "message": "ffmpeg is not installed or not in PATH.",
                },
                ensure_ascii=False,
            )

        if shutil.which("ffprobe") is None:
            return json.dumps(
                {
                    "status": "error",
                    "message": "ffprobe is not installed or not in PATH.",
                },
                ensure_ascii=False,
            )

        clip_paths = self._extract_clip_paths(clips_text)
        if not clip_paths:
            return json.dumps(
                {
                    "status": "error",
                    "message": "No MP4 clip paths were found in clips_text.",
                },
                ensure_ascii=False,
            )

        missing = [str(path) for path in clip_paths if not path.exists()]
        if missing:
            return json.dumps(
                {
                    "status": "error",
                    "message": "Some clip files do not exist.",
                    "missing_files": missing,
                },
                ensure_ascii=False,
            )

        narration_path = Path(audio_path).expanduser()
        if not narration_path.exists():
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Audio file not found: {narration_path}",
                },
                ensure_ascii=False,
            )

        audio_duration = self._probe_duration_seconds(narration_path)
        if audio_duration is None:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Could not read audio duration: {narration_path}",
                },
                ensure_ascii=False,
            )

        target_per_clip = audio_duration / len(clip_paths)
        balanced_timeline: list[Path] = []
        repeats_by_clip: dict[str, int] = {}

        for clip in clip_paths:
            clip_duration = self._probe_duration_seconds(clip)
            if clip_duration is None:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"Could not read clip duration: {clip}",
                    },
                    ensure_ascii=False,
                )

            repeat_count = max(1, int((target_per_clip / clip_duration) + 0.999))
            repeats_by_clip[str(clip)] = repeat_count
            for _ in range(repeat_count):
                balanced_timeline.append(clip)

        output_file = Path(output_path).expanduser()
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as list_file:
            concat_file = Path(list_file.name)
            for clip in balanced_timeline:
                list_file.write(f"file '{clip.resolve().as_posix()}'\n")

# 1. Schritt: Concat (Wir kopieren hier noch, um Zeit zu sparen)
        concatenated_temp = output_file.with_suffix(".concat.mp4")
        concat_command = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(concatenated_temp),
        ]
        
        self._run_command(concat_command)

        # 2. Schritt: Muxing mit Erzwingung der Synchronisation
        # Wir nutzen -fflags +genpts, um kaputte Zeitstempel der KI-Videos zu reparieren
        mux_command = [
            "ffmpeg", "-y",
            "-fflags", "+genpts", 
            "-i", str(concatenated_temp),
            "-i", str(narration_path),
            "-map", "0:v:0",        # Video von Input 0
            "-map", "1:a:0",        # Audio von Input 1
            "-c:v", "copy",         # Video weiterhin kopieren (schnell)
            "-c:a", "aac",          # Audio neu kodieren (sicher)
            "-b:a", "192k",
            "-ac", "2",             # Stereo erzwingen
            "-ar", "44100",         # Standard Sampling Rate
            "-af", "aresample=async=1", # Verhindert Audio-Drift
            "-t", f"{audio_duration:.3f}",
            "-movflags", "+faststart",
            str(output_file),
        ]
        mux_code, mux_error = self._run_command(mux_command)

        concat_file.unlink(missing_ok=True)
        concatenated_temp.unlink(missing_ok=True)

        if mux_code != 0:
            return json.dumps(
                {
                    "status": "error",
                    "message": "ffmpeg mux step failed.",
                    "ffmpeg_error": mux_error,
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "status": "success",
                "output_path": str(output_file),
                "resolved_output_path": str(output_file.resolve()),
                "clip_count": len(clip_paths),
                "timeline_clip_count": len(balanced_timeline),
                "audio_duration_seconds": round(audio_duration, 3),
                "target_seconds_per_clip": round(target_per_clip, 3),
                "repeats_by_clip": repeats_by_clip,
                "audio_path": str(narration_path),
            },
            ensure_ascii=False,
        )
