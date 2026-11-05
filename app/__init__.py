"""Paper-to-World: turn a research paper into an interactive 2D/3D lesson.

Settings come from the environment; a .env file in the working directory is read first, before any module
reads its settings.
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path.cwd() / ".env")
