"""
Gemini CLI agent runner.
"""

import asyncio
import os
import re
from pathlib import Path
from typing import Callable

from ..config import config
from .base import AgentRunner, AgentCommand


def _normalize_path(path: str) -> str:
    """Normalize a path for comparison: expanduser, abspath, normpath."""
    return os.path.normpath(os.path.abspath(os.path.expanduser(path)))


def _find_gemini_project_dir(working_directory: str) -> Path | None:
    """
    Find the Gemini tmp directory that corresponds to the given working directory.

    Gemini CLI stores sessions in ~/.gemini/tmp/<name>/chats/
    Each project directory contains a .project_root file with the absolute
    path of the associated project. Scans all subdirectories and reads their
    .project_root files to find the one matching working_directory.

    Args:
        working_directory: The project directory to find.

    Returns:
        Path to the matching project directory, or None if not found.
    """
    gemini_tmp = Path.home() / ".gemini" / "tmp"
    if not gemini_tmp.exists():
        return None

    normalized_wd = _normalize_path(working_directory)

    try:
        for subdir in gemini_tmp.iterdir():
            if not subdir.is_dir():
                continue
            project_root_file = subdir / ".project_root"
            if not project_root_file.exists():
                continue
            try:
                stored_path = project_root_file.read_text().rstrip("\r\n")
                if not stored_path:
                    continue
                if _normalize_path(stored_path) == normalized_wd:
                    return subdir
            except (OSError, UnicodeDecodeError):
                continue
    except OSError:
        return None

    return None


async def get_gemini_session_for_project(
    working_directory: str | None = None,
    since_mtime: float | None = None,
    max_retries: int = 3,
    retry_delay: float = 0.3,
) -> bool:
    """
    Check if a Gemini session exists for the given project.

    Gemini stores sessions in ~/.gemini/tmp/<name>/chats/session-*.json
    where <name> is identified by reading the .project_root file in each
    subdirectory to match against the working_directory.

    Args:
        working_directory: The project directory to scope to.
        since_mtime: Only consider sessions created after this timestamp.
        max_retries: Number of retries if no session found.
        retry_delay: Delay between retries in seconds.

    Returns:
        True if a valid session exists, False otherwise
    """
    # Require working_directory for project-scoped session discovery
    # Without it, we could accidentally resume a session from a different project
    if not working_directory:
        return False

    for attempt in range(max_retries):
        # Find project dir inside retry loop: on first run, the directory
        # may not exist yet if R1 is still writing
        project_dir = _find_gemini_project_dir(working_directory)
        if project_dir is not None:
            chats_dir = project_dir / "chats"
            if chats_dir.exists():
                try:
                    for session_file in chats_dir.glob("session-*.json"):
                        try:
                            mtime = session_file.stat().st_mtime
                            if since_mtime is None or mtime >= since_mtime:
                                return True
                        except OSError:
                            continue
                except OSError:
                    pass

        # Retry with delay if no session found
        # Uses asyncio.sleep to avoid blocking the event loop
        if attempt < max_retries - 1:
            await asyncio.sleep(retry_delay)

    return False


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

        # Use -p/--prompt for non-interactive (headless) mode
        # Without -p, Gemini enters interactive mode and never exits
        # The -p flag takes the prompt as its value, so prompts starting
        # with - are safe (they're the flag's argument, not parsed as flags)
        full_command.extend(["-p", prompt])

        return AgentCommand(
            command=full_command,
            prompt="",  # Prompt is in command via -p flag
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

        # Use -p for non-interactive mode (same as exec)
        full_command.extend(["-p", prompt])

        return AgentCommand(
            command=full_command,
            prompt="",  # Prompt is in command via -p flag
            cwd=working_directory,
            output_prefix="Gemini Resume Output",
            not_found_hint="Please ensure Gemini CLI is installed (npm install -g @google/gemini-cli).",
            stream=False,  # Resume uses non-streaming mode
        )

    def get_output_cleaner(self) -> Callable[[str, str], str]:
        return clean_gemini_output

    async def parse_session_id(
        self,
        output: str,
        since_mtime: float | None = None,
        working_directory: str | None = None,
    ) -> str | None:
        """
        Get session ID for Gemini.

        Gemini CLI uses index numbers for resume (-r 1), not UUIDs.
        We return "1" (most recent by index) only if we verify that a session
        was actually created for this project since since_mtime.

        Note: Gemini's -r flag uses 1-indexed session ordering where 1 is most recent.
        The ordering is chronological within the project's session directory.
        We find the project directory by matching .project_root file contents
        against the working_directory.

        Args:
            output: Ignored (Gemini doesn't output session IDs)
            since_mtime: Only consider sessions created after this timestamp
            working_directory: Project directory to scope session search

        Returns:
            "1" if a valid session exists for this project, None otherwise
        """
        # Check if a session was created for this project
        if await get_gemini_session_for_project(
            working_directory=working_directory,
            since_mtime=since_mtime,
        ):
            # Return "1" as the session index - it refers to the most recent session
            # Project is identified by .project_root file matching
            return "1"
        return None

    def validate_session_id(self, session_id: str) -> bool:
        """
        Validate a Gemini session ID.

        Gemini uses numeric indices (1-indexed) or "latest" for session references.
        Index 0 is invalid as Gemini uses 1-based indexing.
        """
        if not session_id:
            return False
        # Accept numeric indices >= 1 (Gemini uses 1-indexed sessions)
        if session_id.isdigit():
            return int(session_id) >= 1
        # Accept "latest"
        if session_id == "latest":
            return True
        # Reject anything that looks like a flag
        if session_id.startswith("-"):
            return False
        return False
