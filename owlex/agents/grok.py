"""
Grok agent runner via OpenCode CLI with xAI backend.
Uses OpenCode with xAI/Grok models for council deliberation and coding tasks.
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Callable

from ..config import config
from .base import AgentRunner, AgentCommand


def _get_grok_project_id(working_directory: str) -> str | None:
    """
    Look up the projectID that OpenCode uses for session storage.
    Reuses OpenCode's project registry since Grok runs through OpenCode.
    """
    project_dir = Path.home() / ".local" / "share" / "opencode" / "storage" / "project"
    if not project_dir.exists():
        return None

    abs_path = os.path.abspath(working_directory)

    try:
        for project_file in project_dir.glob("*.json"):
            if project_file.name == "global.json":
                continue
            try:
                with open(project_file) as f:
                    project_data = json.load(f)
                    if project_data.get("worktree") == abs_path:
                        return project_data.get("id")
            except (json.JSONDecodeError, OSError):
                continue
    except OSError:
        return None

    return None


async def get_latest_grok_session(
    working_directory: str | None = None,
    since_mtime: float | None = None,
    max_retries: int = 3,
    retry_delay: float = 0.3,
) -> str | None:
    """
    Find the most recent Grok/OpenCode session ID from filesystem.
    Grok uses OpenCode's session storage since it runs through the OpenCode CLI.
    """
    opencode_dir = Path.home() / ".local" / "share" / "opencode" / "storage" / "session"
    if not opencode_dir.exists():
        return None

    if not working_directory:
        return None

    project_id = _get_grok_project_id(working_directory)
    if not project_id:
        return None

    for attempt in range(max_retries):
        latest_file: Path | None = None
        latest_mtime: float = 0

        project_dirs = [opencode_dir / project_id]

        for project_dir in project_dirs:
            if not project_dir.exists():
                continue
            try:
                for session_file in project_dir.glob("ses_*.json"):
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
                continue

        if latest_file is not None:
            return latest_file.stem

        if attempt < max_retries - 1:
            await asyncio.sleep(retry_delay)

    return None


def clean_grok_output(raw_output: str, original_prompt: str = "") -> str:
    """Clean Grok/OpenCode CLI output by removing noise."""
    if not config.grok.clean_output:
        return raw_output
    cleaned = raw_output
    # Remove ANSI escape codes
    cleaned = re.sub(r'\x1b\[[0-9;]*m', '', cleaned)
    # Collapse multiple newlines
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


class GrokRunner(AgentRunner):
    """
    Runner for Grok models via OpenCode CLI.

    Uses OpenCode with xAI/Grok models. Requires XAI_API_KEY environment variable.

    Two model configurations:
    - GROK_MODEL: Model for council deliberation (default: xai/grok-4-1-fast-reasoning)
    - GROK_CODE_MODEL: Model for coding tasks (default: xai/grok-code-fast-1)
    """

    @property
    def name(self) -> str:
        return "grok"

    def _get_model(self, for_coding: bool = False) -> str:
        """Get the appropriate Grok model based on task type."""
        if for_coding:
            return config.grok.code_model
        return config.grok.model

    def build_exec_command(
        self,
        prompt: str,
        working_directory: str | None = None,
        enable_search: bool = False,
        for_coding: bool = False,
        **kwargs,
    ) -> AgentCommand:
        """Build command for running Grok via OpenCode with a prompt."""
        full_command = ["opencode", "run"]

        # Model configuration - use Grok model
        model = self._get_model(for_coding=for_coding)
        full_command.extend(["--model", model])

        # Agent selection (reuse OpenCode's agent config)
        if config.grok.agent:
            full_command.extend(["--agent", config.grok.agent])

        # Use -- to signal end of options
        full_command.append("--")
        full_command.append(prompt)

        return AgentCommand(
            command=full_command,
            prompt="",  # Prompt is in command as positional arg
            cwd=working_directory,
            output_prefix="Grok Output",
            not_found_hint="Please ensure OpenCode is installed (curl -fsSL https://opencode.ai/install | bash) and XAI_API_KEY is set.",
            stream=True,
        )

    def build_resume_command(
        self,
        session_ref: str,
        prompt: str,
        working_directory: str | None = None,
        enable_search: bool = False,
        for_coding: bool = False,
        **kwargs,
    ) -> AgentCommand:
        """Build command for resuming an existing Grok/OpenCode session."""
        full_command = ["opencode", "run"]

        # Model configuration
        model = self._get_model(for_coding=for_coding)
        full_command.extend(["--model", model])

        # Agent selection
        if config.grok.agent:
            full_command.extend(["--agent", config.grok.agent])

        # Session resume
        if session_ref == "--continue" or session_ref == "latest":
            full_command.append("--continue")
        else:
            if session_ref.startswith("-"):
                raise ValueError(f"Invalid session_ref: '{session_ref}' - cannot start with '-'")
            full_command.extend(["--session", session_ref])

        full_command.append("--")
        full_command.append(prompt)

        return AgentCommand(
            command=full_command,
            prompt="",
            cwd=working_directory,
            output_prefix="Grok Resume Output",
            not_found_hint="Please ensure OpenCode is installed (curl -fsSL https://opencode.ai/install | bash) and XAI_API_KEY is set.",
            stream=False,
        )

    def get_output_cleaner(self) -> Callable[[str, str], str]:
        return clean_grok_output

    async def parse_session_id(
        self,
        output: str,
        since_mtime: float | None = None,
        working_directory: str | None = None,
    ) -> str | None:
        """
        Get session ID for Grok.
        Uses OpenCode's session storage since Grok runs through OpenCode.
        """
        return await get_latest_grok_session(
            working_directory=working_directory,
            since_mtime=since_mtime,
        )
