"""
Agent runners for owlex.
Each agent knows how to construct and run its specific CLI commands.
"""

from .base import AgentRunner
from .aider import AiderRunner
from .codex import CodexRunner
from .gemini import GeminiRunner
from .opencode import OpenCodeRunner

__all__ = ["AgentRunner", "AiderRunner", "CodexRunner", "GeminiRunner", "OpenCodeRunner"]
