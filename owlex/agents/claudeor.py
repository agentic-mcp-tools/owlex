"""
Claude Code via OpenRouter agent runner.
Uses Claude CLI with OpenRouter as the backend for alternative models.
"""

import asyncio
import hashlib
import re
from pathlib import Path
from typing import Callable

from ..config import config
from .base import AgentRunner, AgentCommand


async def get_latest_claude_session(
    working_directory: str | None = None,
    since_mtime: float | None = None,
    max_retries: int = 3,
    retry_delay: float = 0.3,
) -> str | None:
    """
    Find the most recent Claude session ID from filesystem.

    Claude stores sessions in ~/.claude/projects/<project-hash>/sessions/
    or uses a project-specific structure.

    Args:
        working_directory: Working directory to scope session discovery.
        since_mtime: Only consider files modified after this timestamp.
        max_retries: Number of retries if no session found.
        retry_delay: Delay between retries in seconds.

    Returns:
        Session ID if found, None otherwise
    """
    claude_dir = Path.home() / ".claude"
    if not claude_dir.exists():
        return None

    # Claude uses project hashes for session organization
    projects_dir = claude_dir / "projects"
    if not projects_dir.exists():
        return None

    for attempt in range(max_retries):
        latest_file: Path | None = None
        latest_mtime: float = 0

        # If working directory provided, look for project-specific sessions
        if working_directory:
            # Claude hashes the project path
            project_path = Path(working_directory).resolve()
            # Try to find matching project directory
            for project_dir in projects_dir.iterdir():
                if not project_dir.is_dir():
                    continue
                # Look for session files in this project
                for session_file in project_dir.glob("*.jsonl"):
                    try:
                        mtime = session_file.stat().st_mtime
                        if since_mtime is not None and mtime < since_mtime:
                            continue
                        if mtime > latest_mtime:
                            latest_mtime = mtime
                            latest_file = session_file
                    except OSError:
                        continue
        else:
            # Search all project directories for recent sessions
            try:
                for project_dir in projects_dir.iterdir():
                    if not project_dir.is_dir():
                        continue
                    for session_file in project_dir.glob("*.jsonl"):
                        try:
                            mtime = session_file.stat().st_mtime
                            if since_mtime is not None and mtime < since_mtime:
                                continue
                            if mtime > latest_mtime:
                                latest_mtime = mtime
                                latest_file = session_file
                        except OSError:
                            continue
            except OSError:
                pass

        if latest_file is not None:
            # Return the session file stem as the session ID
            return latest_file.stem

        if attempt < max_retries - 1:
            await asyncio.sleep(retry_delay)

    return None


def clean_claudeor_output(raw_output: str, original_prompt: str = "") -> str:
    """Clean Claude OpenRouter output."""
    if not config.claudeor.clean_output:
        return raw_output
    cleaned = raw_output
    # Remove excessive newlines
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


class ClaudeORRunner(AgentRunner):
    """Runner for Claude Code CLI via OpenRouter."""

    @property
    def name(self) -> str:
        return "claudeor"

    def _get_env_overrides(self) -> dict[str, str]:
        """Get environment variable overrides for OpenRouter."""
        env = {
            "ANTHROPIC_BASE_URL": "https://openrouter.ai/api",
            "ANTHROPIC_API_KEY": "",  # Must be empty
        }

        # Use API key from config
        if config.claudeor.api_key:
            env["ANTHROPIC_AUTH_TOKEN"] = config.claudeor.api_key

        # Set model override if specified
        if config.claudeor.model:
            env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = config.claudeor.model

        return env

    def build_exec_command(
        self,
        prompt: str,
        working_directory: str | None = None,
        enable_search: bool = False,
        **kwargs,
    ) -> AgentCommand:
        """Build command for starting a new Claude OpenRouter session."""
        full_command = ["claude"]

        # Use print mode for single-shot execution
        full_command.extend(["--print", "-p", prompt])

        # Set working directory if provided
        cwd = working_directory

        return AgentCommand(
            command=full_command,
            prompt="",  # Prompt is in command args
            cwd=cwd,
            output_prefix="Claude (OpenRouter) Output",
            not_found_hint="Please ensure Claude CLI is installed. Run: npm install -g @anthropic-ai/claude-code",
            stream=False,  # Print mode doesn't stream
            env_overrides=self._get_env_overrides(),
        )

    def build_resume_command(
        self,
        session_ref: str,
        prompt: str,
        working_directory: str | None = None,
        enable_search: bool = False,
        **kwargs,
    ) -> AgentCommand:
        """Build command for resuming an existing Claude session."""
        full_command = ["claude"]

        # Resume with session reference
        if session_ref == "--continue" or session_ref == "continue":
            full_command.append("--continue")
        else:
            # Validate session_ref
            if session_ref.startswith("-"):
                raise ValueError(f"Invalid session_ref: '{session_ref}' - cannot start with '-'")
            full_command.extend(["--resume", session_ref])

        # Use print mode
        full_command.extend(["--print", "-p", prompt])

        cwd = working_directory

        return AgentCommand(
            command=full_command,
            prompt="",  # Prompt is in command args
            cwd=cwd,
            output_prefix="Claude (OpenRouter) Output",
            not_found_hint="Please ensure Claude CLI is installed. Run: npm install -g @anthropic-ai/claude-code",
            stream=False,
            env_overrides=self._get_env_overrides(),
        )

    def get_output_cleaner(self) -> Callable[[str, str], str]:
        return clean_claudeor_output

    async def parse_session_id(
        self,
        output: str,
        since_mtime: float | None = None,
        working_directory: str | None = None,
    ) -> str | None:
        """
        Get session ID for Claude.

        Claude stores sessions in project-specific directories.
        """
        return await get_latest_claude_session(
            working_directory=working_directory,
            since_mtime=since_mtime,
        )
