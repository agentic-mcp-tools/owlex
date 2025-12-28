"""
Gemini CLI agent runner.
"""

import re
from pathlib import Path
from typing import Callable

from ..config import config
from .base import AgentRunner, AgentCommand


def get_latest_gemini_session() -> str | None:
    """
    Find the most recent Gemini session ID from filesystem.

    Gemini stores sessions in ~/.gemini/tmp/<hash>/chats/session-*.json
    The short UUID is extracted from the filename.

    Returns:
        Session UUID (short form) if found, None otherwise
    """
    gemini_dir = Path.home() / ".gemini" / "tmp"
    if not gemini_dir.exists():
        return None

    # Find the most recent session file across all project directories
    latest_file: Path | None = None
    latest_mtime: float = 0

    for project_dir in gemini_dir.iterdir():
        if not project_dir.is_dir():
            continue
        chats_dir = project_dir / "chats"
        if not chats_dir.exists():
            continue
        for session_file in chats_dir.glob("session-*.json"):
            mtime = session_file.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_file = session_file

    if latest_file is None:
        return None

    # Extract UUID from filename: session-YYYY-MM-DDTHH-MM-<short-uuid>.json
    # Pattern: session-2025-12-27T16-07-f44b0544.json
    filename = latest_file.stem  # Remove .json
    match = re.search(r'session-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-([a-f0-9]+)$', filename)
    if match:
        return match.group(1)

    return None


def clean_gemini_output(raw_output: str, original_prompt: str = "") -> str:
    """Clean Gemini CLI output by removing noise."""
    if not config.gemini.clean_output:
        return raw_output
    cleaned = raw_output
    if cleaned.startswith("YOLO mode is enabled."):
        lines = cleaned.split('\n', 2)
        if len(lines) > 2:
            cleaned = lines[2]
        elif len(lines) > 1:
            cleaned = lines[1]
    cleaned = re.sub(r'^Loaded cached credentials\.\n?', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


class GeminiRunner(AgentRunner):
    """Runner for Google Gemini CLI."""

    @property
    def name(self) -> str:
        return "gemini"

    def build_exec_command(
        self,
        prompt: str,
        working_directory: str | None = None,
        enable_search: bool = False,  # Gemini doesn't have search flag
        **kwargs,
    ) -> AgentCommand:
        """Build command for starting a new Gemini session."""
        full_command = ["gemini"]

        if config.gemini.yolo_mode:
            full_command.extend(["--approval-mode", "yolo"])

        if working_directory:
            full_command.extend(["--include-directories", working_directory])

        # Pass prompt via stdin to prevent prompt-as-flag injection
        # Gemini reads from stdin when no positional prompt is provided
        # This ensures prompts starting with - aren't parsed as CLI flags
        return AgentCommand(
            command=full_command,
            prompt=prompt,  # Prompt passed via stdin
            cwd=working_directory,
            output_prefix="Gemini Output",
            not_found_hint="Please ensure Gemini CLI is installed (npm install -g @google/gemini-cli).",
            stream=True,
        )

    def build_resume_command(
        self,
        session_ref: str,
        prompt: str,
        working_directory: str | None = None,
        enable_search: bool = False,
        **kwargs,
    ) -> AgentCommand:
        """Build command for resuming an existing Gemini session."""
        full_command = ["gemini"]

        if config.gemini.yolo_mode:
            full_command.extend(["--approval-mode", "yolo"])

        if working_directory:
            full_command.extend(["--include-directories", working_directory])

        full_command.extend(["-r", session_ref])

        # Pass prompt via stdin to prevent prompt-as-flag injection
        return AgentCommand(
            command=full_command,
            prompt=prompt,  # Prompt passed via stdin
            cwd=working_directory,
            output_prefix="Gemini Resume Output",
            not_found_hint="Please ensure Gemini CLI is installed (npm install -g @google/gemini-cli).",
            stream=False,  # Resume uses non-streaming mode
        )

    def get_output_cleaner(self) -> Callable[[str, str], str]:
        return clean_gemini_output

    def parse_session_id(self, output: str) -> str | None:
        """
        Get session ID for Gemini.

        Gemini doesn't output session ID in stdout, so we check the filesystem
        for the most recently created session file. Returns short UUID prefix.

        Note: Gemini CLI uses index numbers for resume (--resume 1), not UUIDs.
        For now, we return "1" (most recent by index) since we call this right
        after R1 completes and session 1 will be our R1 session.
        """
        # Return "1" as the session index - it refers to the most recent session
        # This is safer than "latest" because indices are project-scoped
        # TODO: Consider parsing the full UUID and matching against --list-sessions
        return "1"
