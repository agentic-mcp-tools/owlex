"""
OpenCode CLI agent runner.
"""

import re
from pathlib import Path
from typing import Callable

from ..config import config
from .base import AgentRunner, AgentCommand


def get_latest_opencode_session() -> str | None:
    """
    Find the most recent OpenCode session ID from filesystem.

    OpenCode stores sessions in ~/.local/share/opencode/storage/session/<project>/ses_*.json
    The session ID is extracted from the filename (without .json extension).

    Returns:
        Session ID (e.g., ses_49b5d1b81ffeZfa2uTg3NVmKrH) if found, None otherwise
    """
    opencode_dir = Path.home() / ".local" / "share" / "opencode" / "storage" / "session"
    if not opencode_dir.exists():
        return None

    # Find the most recent session file across all project directories
    latest_file: Path | None = None
    latest_mtime: float = 0

    for project_dir in opencode_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for session_file in project_dir.glob("ses_*.json"):
            mtime = session_file.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_file = session_file

    if latest_file is None:
        return None

    # Session ID is the filename without .json extension
    return latest_file.stem


def clean_opencode_output(raw_output: str, original_prompt: str = "") -> str:
    """Clean OpenCode CLI output by removing noise."""
    if not config.opencode.clean_output:
        return raw_output
    cleaned = raw_output
    # Remove ANSI escape codes
    cleaned = re.sub(r'\x1b\[[0-9;]*m', '', cleaned)
    # Collapse multiple newlines
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


class OpenCodeRunner(AgentRunner):
    """Runner for OpenCode AI coding agent CLI."""

    @property
    def name(self) -> str:
        return "opencode"

    def build_exec_command(
        self,
        prompt: str,
        working_directory: str | None = None,
        enable_search: bool = False,  # OpenCode doesn't have web search flag
        **kwargs,
    ) -> AgentCommand:
        """Build command for running OpenCode with a prompt."""
        full_command = ["opencode", "run"]

        # Model configuration (format: provider/model)
        if config.opencode.model:
            full_command.extend(["--model", config.opencode.model])

        # Agent selection (e.g., "build", "plan")
        if config.opencode.agent:
            full_command.extend(["--agent", config.opencode.agent])

        # Output format
        if config.opencode.json_output:
            full_command.extend(["--format", "json"])

        # Use -- to signal end of options, preventing prompt-as-flag injection
        # This ensures prompts starting with - aren't parsed as CLI flags
        full_command.append("--")
        full_command.append(prompt)

        return AgentCommand(
            command=full_command,
            prompt="",  # Prompt is in command as positional arg
            cwd=working_directory,
            output_prefix="OpenCode Output",
            not_found_hint="Please ensure OpenCode is installed (curl -fsSL https://opencode.ai/install | bash).",
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
        """Build command for resuming an existing OpenCode session."""
        full_command = ["opencode", "run"]

        # Model configuration
        if config.opencode.model:
            full_command.extend(["--model", config.opencode.model])

        # Agent selection
        if config.opencode.agent:
            full_command.extend(["--agent", config.opencode.agent])

        # Output format
        if config.opencode.json_output:
            full_command.extend(["--format", "json"])

        # Session resume
        if session_ref == "--continue" or session_ref == "latest":
            full_command.append("--continue")
        else:
            # Validate session_ref to prevent flag injection
            if session_ref.startswith("-"):
                raise ValueError(f"Invalid session_ref: '{session_ref}' - cannot start with '-'")
            full_command.extend(["--session", session_ref])

        # Use -- to signal end of options, preventing prompt-as-flag injection
        full_command.append("--")
        full_command.append(prompt)

        return AgentCommand(
            command=full_command,
            prompt="",  # Prompt is in command as positional arg
            cwd=working_directory,
            output_prefix="OpenCode Resume Output",
            not_found_hint="Please ensure OpenCode is installed (curl -fsSL https://opencode.ai/install | bash).",
            stream=False,  # Resume uses non-streaming mode
        )

    def get_output_cleaner(self) -> Callable[[str, str], str]:
        return clean_opencode_output

    def parse_session_id(self, output: str) -> str | None:
        """
        Get session ID for OpenCode.

        OpenCode doesn't output session ID in stdout, so we check the filesystem
        for the most recently created session file.
        """
        return get_latest_opencode_session()
