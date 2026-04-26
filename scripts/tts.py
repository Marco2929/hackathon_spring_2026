"""Simple CLI for generating speech with edge-tts.

Examples:
	python tts.py --text "Hello from Edge TTS" --out output.mp3
	python tts.py --text-file message.txt --voice en-US-JennyNeural
	python tts.py --list-voices
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import edge_tts


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Text-to-speech with edge-tts")
	parser.add_argument("--text", help="Text to synthesize")
	parser.add_argument("--text-file", help="Path to a UTF-8 text file to synthesize")
	parser.add_argument(
		"--voice",
		default="en-US-AriaNeural",
		help="Voice name (default: en-US-AriaNeural)",
	)
	parser.add_argument(
		"--rate",
		default="+0%",
		help="Speaking rate, e.g. +20%%, -10%% (default: +0%%)",
	)
	parser.add_argument(
		"--volume",
		default="+0%",
		help="Volume adjustment, e.g. +0%%, -20%% (default: +0%%)",
	)
	parser.add_argument(
		"--pitch",
		default="+0Hz",
		help="Pitch adjustment, e.g. +0Hz, -50Hz (default: +0Hz)",
	)
	parser.add_argument(
		"--out",
		default="speech.mp3",
		help="Output audio path (default: speech.mp3)",
	)
	parser.add_argument(
		"--list-voices",
		action="store_true",
		help="List available voices and exit",
	)
	return parser


def resolve_text(args: argparse.Namespace) -> str:
	if args.text and args.text_file:
		raise ValueError("Use either --text or --text-file, not both.")
	if not args.text and not args.text_file:
		raise ValueError("Provide text with --text or --text-file.")

	if args.text:
		return args.text.strip()

	text_file = Path(args.text_file)
	if not text_file.exists():
		raise ValueError(f"Text file not found: {text_file}")

	content = text_file.read_text(encoding="utf-8").strip()
	if not content:
		raise ValueError("Text file is empty.")
	return content


async def print_voices() -> None:
	voices = await edge_tts.list_voices()
	for voice in voices:
		name = voice.get("ShortName", "")
		locale = voice.get("Locale", "")
		gender = voice.get("Gender", "")
		print(f"{name:30} {locale:10} {gender}")


async def synthesize_to_file(
	text: str,
	out_path: Path,
	voice: str,
	rate: str,
	volume: str,
	pitch: str,
) -> None:
	out_path.parent.mkdir(parents=True, exist_ok=True)
	communicate = edge_tts.Communicate(
		text=text,
		voice=voice,
		rate=rate,
		volume=volume,
		pitch=pitch,
	)
	await communicate.save(str(out_path))


def main() -> int:
	parser = build_parser()
	args = parser.parse_args()

	try:
		if args.list_voices:
			asyncio.run(print_voices())
			return 0

		text = resolve_text(args)
		out_path = Path(args.out)
		asyncio.run(
			synthesize_to_file(
				text=text,
				out_path=out_path,
				voice=args.voice,
				rate=args.rate,
				volume=args.volume,
				pitch=args.pitch,
			)
		)
		print(f"Saved speech to: {out_path}")
		return 0
	except KeyboardInterrupt:
		print("Cancelled by user.")
		return 130
	except Exception as exc:  # pragma: no cover
		print(f"Error: {exc}", file=sys.stderr)
		return 1


if __name__ == "__main__":
	raise SystemExit(main())
