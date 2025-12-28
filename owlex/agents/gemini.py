"""
Gemini CLI agent runner.
"""

import re
from typing import Callable

from ..config import config
from .base import AgentRunner, AgentCommand


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
