#!/usr/bin/env python
import sys
import warnings
import shutil
from pathlib import Path


from youtube_crew.crew import YoutubeCrew

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

# This main file is intended to be a way for you to run your
# crew locally, so refrain from adding unnecessary logic into this file.
def _reset_output_directory() -> None:
    project_root = Path(__file__).resolve().parents[2]
    output_dir = project_root / "output"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def run():

    try:
        _reset_output_directory()
        YoutubeCrew().crew().kickoff()
    except Exception as e:
        raise Exception(f"An error occurred while running the crew: {e}")

if __name__ == '__main__':
    run()