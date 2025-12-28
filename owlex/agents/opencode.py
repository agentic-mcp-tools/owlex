"""
OpenCode CLI agent runner.
"""

import hashlib
import re
import time
from pathlib import Path
from typing import Callable

from ..config import config
from .base import AgentRunner, AgentCommand


def _get_opencode_project_hash(working_directory: str) -> str:
    """
    Compute the project hash that OpenCode uses for session storage.

    OpenCode stores sessions in ~/.local/share/opencode/storage/session/<hash>/
    The hash is derived from the working directory path.
    """
    # OpenCode uses SHA1 of the absolute path
    abs_path = Path(working_directory).resolve()
    return hashlib.sha1(str(abs_path).encode()).hexdigest()


def get_latest_opencode_session(
    working_directory: str | None = None,
    since_mtime: float | None = None,
    max_retries: int = 3,
    retry_delay: float = 0.3,
) -> str | None:
    """
    Find the most recent OpenCode session ID from filesystem.

    OpenCode stores sessions in ~/.local/share/opencode/storage/session/<project>/ses_*.json
    The session ID is extracted from the filename (without .json extension).

    Args:
        working_directory: Project directory to scope session search.
        since_mtime: Only consider sessions created after this timestamp.
        max_retries: Number of retries if no session found.
        retry_delay: Delay between retries in seconds.

    Returns:
        Session ID (e.g., ses_49b5d1b81ffeZfa2uTg3NVmKrH) if found, None otherwise
    """
    opencode_dir = Path.home() / ".local" / "share" / "opencode" / "storage" / "session"
    if not opencode_dir.exists():
        return None

    for attempt in range(max_retries):
        latest_file: Path | None = None
        latest_mtime: float = 0

        # If working_directory is specified, only check that project's hash
        if working_directory:
            project_hash = _get_opencode_project_hash(working_directory)
            project_dirs = [opencode_dir / project_hash]
        else:
            # Fallback: check all project directories (less safe)
            try:
                project_dirs = [d for d in opencode_dir.iterdir() if d.is_dir()]
            except OSError:
                return None

        for project_dir in project_dirs:
            if not project_dir.exists():
                continue
            try:
                for session_file in project_dir.glob("ses_*.json"):
                    try:
                        mtime = session_file.stat().st_mtime
                        # Skip files older than since_mtime if specified
                        if since_mtime is not None and mtime < since_mtime:
                            continue
                        if mtime > latest_mtime:
                            latest_mtime = mtime
                            latest_file = session_file
                    except OSError:
                        continue
            except OSError:
                continue

        if latest_file is not None:
            # Session ID is the filename without .json extension
            return latest_file.stem

        # Retry with delay if no session found
        if attempt < max_retries - 1:
            time.sleep(retry_delay)

    return None


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

    def parse_session_id(
        self,
        output: str,
        since_mtime: float | None = None,
        working_directory: str | None = None,
    ) -> str | None:
        """
        Get session ID for OpenCode.

        OpenCode doesn't output session ID in stdout, so we check the filesystem
        for the most recently created session file.

        Args:
            output: Ignored (OpenCode doesn't output session IDs)
            since_mtime: Only consider sessions created after this timestamp
            working_directory: Project directory to scope session search
        """
        return get_latest_opencode_session(
            working_directory=working_directory,
            since_mtime=since_mtime,
        )
