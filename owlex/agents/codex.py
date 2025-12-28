"""
Codex CLI agent runner.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..config import config
from .base import AgentRunner, AgentCommand


def get_latest_codex_session() -> str | None:
    """
    Find the most recent Codex session ID from filesystem.

    Codex stores sessions in ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
    The UUID is extracted from the filename.

    Returns:
        Session UUID if found, None otherwise
    """
    codex_dir = Path.home() / ".codex" / "sessions"
    if not codex_dir.exists():
        return None

    # Find the most recent session file across all date directories
    latest_file: Path | None = None
    latest_mtime: float = 0

    # Check recent date directories (today and yesterday to handle timezone edge cases)
    now = datetime.now()
    date_dirs = [
        codex_dir / f"{now.year}" / f"{now.month:02d}" / f"{now.day:02d}",
        codex_dir / f"{now.year}" / f"{now.month:02d}" / f"{now.day - 1:02d}" if now.day > 1 else None,
    ]

    for date_dir in date_dirs:
        if date_dir is None or not date_dir.exists():
            continue
        for session_file in date_dir.glob("rollout-*.jsonl"):
            mtime = session_file.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_file = session_file

    if latest_file is None:
        return None

    # Extract UUID from filename: rollout-YYYY-MM-DDTHH-MM-SS-<UUID>.jsonl
    # The UUID is the last hyphen-separated segment before .jsonl
    filename = latest_file.stem  # Remove .jsonl
    # Pattern: rollout-2025-12-28T13-33-54-019b64bc-81d9-7ba1-821d-b90ccfc8876f
    match = re.search(r'rollout-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-([a-f0-9-]+)$', filename)
    if match:
        return match.group(1)

    return None


def clean_codex_output(raw_output: str, original_prompt: str = "") -> str:
    """Clean Codex CLI output by removing echoed prompt templates."""
    if not config.codex.clean_output:
        return raw_output
    cleaned = raw_output
    if original_prompt and cleaned.startswith(original_prompt):
        cleaned = cleaned[len(original_prompt):].lstrip()
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


class CodexRunner(AgentRunner):
    """Runner for OpenAI Codex CLI."""

    @property
    def name(self) -> str:
        return "codex"

    def build_exec_command(
        self,
        prompt: str,
        working_directory: str | None = None,
        enable_search: bool = False,
        **kwargs,
    ) -> AgentCommand:
        """Build command for starting a new Codex session."""
        full_command = ["codex", "exec", "--skip-git-repo-check"]

        if working_directory:
            full_command.extend(["--cd", working_directory])
        if enable_search:
            full_command.extend(["--enable", "web_search_request"])

        if config.codex.bypass_approvals:
            full_command.append("--dangerously-bypass-approvals-and-sandbox")
        else:
            full_command.append("--full-auto")

        # Use stdin for prompt input
        full_command.append("-")

        return AgentCommand(
            command=full_command,
            prompt=prompt,
            output_prefix="Codex Output",
            not_found_hint="Please ensure Codex CLI is installed and in your PATH.",
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
        """Build command for resuming an existing Codex session."""
        full_command = ["codex", "exec", "--skip-git-repo-check"]

        if working_directory:
            full_command.extend(["--cd", working_directory])
        if enable_search:
            full_command.extend(["--enable", "web_search_request"])

        if config.codex.bypass_approvals:
            full_command.append("--dangerously-bypass-approvals-and-sandbox")
        else:
            full_command.append("--full-auto")

        full_command.append("resume")
        if session_ref == "--last":
            full_command.append("--last")
        else:
            # Validate session_ref to prevent flag injection
            # Session IDs should be alphanumeric/UUID-like
            if session_ref.startswith("-"):
                raise ValueError(f"Invalid session_ref: '{session_ref}' - cannot start with '-'")
            full_command.append(session_ref)

        # Use stdin for prompt input
        full_command.append("-")

        return AgentCommand(
            command=full_command,
            prompt=prompt,
            output_prefix="Codex Resume Output",
            not_found_hint="Please ensure Codex CLI is installed and in your PATH.",
            stream=False,  # Resume uses non-streaming mode
        )

    def get_output_cleaner(self) -> Callable[[str, str], str]:
        return clean_codex_output

    def parse_session_id(self, output: str) -> str | None:
        """
        Get session ID for Codex.

        Codex doesn't output session ID in stdout, so we check the filesystem
        for the most recently created session file.
        """
        return get_latest_codex_session()
