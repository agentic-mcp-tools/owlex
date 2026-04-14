"""
Claude Code via OpenRouter agent runner.

Uses a direct HTTP call to OpenRouter's chat completions API instead of the
Claude CLI, which returns empty responses in --print mode through OpenRouter.
"""

import re
import sys
from pathlib import Path
from typing import Callable

from ..config import config
from .base import AgentRunner, AgentCommand

# Path to the standalone API script (same directory as this module)
_API_SCRIPT = str(Path(__file__).with_name("claudeor_api.py"))


def clean_claudeor_output(raw_output: str, original_prompt: str = "") -> str:
    """Clean Claude OpenRouter output."""
    if not config.claudeor.clean_output:
        return raw_output
    cleaned = raw_output
    # Remove excessive newlines
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


class ClaudeORRunner(AgentRunner):
    """Runner for OpenRouter API (direct HTTP, no Claude CLI dependency)."""

    @property
    def name(self) -> str:
        return "claudeor"

    def _get_env_overrides(self) -> dict[str, str]:
        """Get environment variable overrides for the API script."""
        import os

        env: dict[str, str] = {}

        api_key = (
            config.claudeor.api_key
            or os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("CLAUDEOR_API_KEY")
        )
        if api_key:
            env["OPENROUTER_API_KEY"] = api_key

        model = config.claudeor.model or os.environ.get("CLAUDEOR_MODEL")
        if model:
            env["CLAUDEOR_MODEL"] = model

        return env

    def build_exec_command(
        self,
        prompt: str,
        working_directory: str | None = None,
        enable_search: bool = False,
        **kwargs,
    ) -> AgentCommand:
        """Build command for calling OpenRouter API directly."""
        return AgentCommand(
            command=[sys.executable, _API_SCRIPT],
            prompt=prompt,  # Sent via stdin
            cwd=working_directory,
            output_prefix="Claude (OpenRouter) Output",
            not_found_hint="Python3 is required to run the OpenRouter API script.",
            stream=False,
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
        """
        Resume is not supported for direct API mode (stateless).
        Falls back to a fresh exec call with the full prompt.
        """
        return self.build_exec_command(
            prompt=prompt,
            working_directory=working_directory,
            enable_search=enable_search,
            **kwargs,
        )

    def get_output_cleaner(self) -> Callable[[str, str], str]:
        return clean_claudeor_output

    async def parse_session_id(
        self,
        output: str,
        since_mtime: float | None = None,
        working_directory: str | None = None,
    ) -> str | None:
        """Direct API mode is stateless — no session to resume."""
        return None
