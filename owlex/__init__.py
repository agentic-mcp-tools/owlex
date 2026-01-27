"""
Owlex - MCP server for multi-agent CLI orchestration.
"""

from importlib.metadata import version

__version__ = version("owlex")

from .models import (
    Task,
    TaskStatus,
    Agent,
    TaskResponse,
    AgentResponse,
    ClaudeOpinion,
    CouncilResponse,
    CouncilRound,
    CouncilMetadata,
)
from .engine import TaskEngine, engine
from .roles import (
    RoleId,
    RoleDefinition,
    TeamPreset,
    RoleResolver,
    RoleSpec,
    BUILTIN_ROLES,
    BUILTIN_TEAMS,
    get_resolver,
)

__all__ = [
    "__version__",
    "Task",
    "TaskStatus",
    "Agent",
    "TaskResponse",
    "AgentResponse",
    "ClaudeOpinion",
    "CouncilResponse",
    "CouncilRound",
    "CouncilMetadata",
    "TaskEngine",
    "engine",
    # Role system
    "RoleId",
    "RoleDefinition",
    "TeamPreset",
    "RoleResolver",
    "RoleSpec",
    "BUILTIN_ROLES",
    "BUILTIN_TEAMS",
    "get_resolver",
]
