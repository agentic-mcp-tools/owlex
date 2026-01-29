"""
Specialist Role System ("Hats") for council deliberation.

Enables agents to operate with specialized perspectives during council sessions.
Supports three modes of role specification:
1. Explicit mapping: {"codex": "security", "gemini": "perf"}
2. Role list with auto-assign: ["security", "perf", "skeptic"]
3. Team presets: "security_audit"
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Sequence, TypeAlias


class RoleId(str, Enum):
    """Built-in role identifiers."""
    SECURITY = "security"
    PERFORMANCE = "perf"
    SKEPTIC = "skeptic"
    ARCHITECT = "architect"
    MAINTAINER = "maintainer"
    DX = "dx"  # Developer Experience
    TESTING = "testing"
    NEUTRAL = "neutral"  # Default: no role injection


@dataclass(frozen=True)
class RoleDefinition:
    """Definition of a specialist role with prompts for each round."""
    id: str
    name: str
    description: str
    round_1_prefix: str  # Prepended to R1 prompt
    round_2_prefix: str  # Prepended to R2 deliberation prompt (sticky role)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "round_1_prefix": self.round_1_prefix,
            "round_2_prefix": self.round_2_prefix,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RoleDefinition:
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            round_1_prefix=data["round_1_prefix"],
            round_2_prefix=data["round_2_prefix"],
        )


@dataclass(frozen=True)
class TeamPreset:
    """Predefined team composition with role assignments."""
    id: str
    name: str
    description: str
    # Maps agent name -> role_id (e.g., {"codex": "security", "gemini": "perf"})
    assignments: dict[str, str]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "assignments": dict(self.assignments),
        }

    @classmethod
    def from_dict(cls, data: dict) -> TeamPreset:
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            assignments=data["assignments"],
        )


# Type aliases for role specification modes
RoleMapping: TypeAlias = dict[str, str]  # {"codex": "security", "gemini": "perf"}
RoleList: TypeAlias = list[str]  # ["security", "perf", "skeptic"]
RoleSpec: TypeAlias = RoleMapping | RoleList | str | None  # str = team preset ID


# === Built-in Role Definitions ===

BUILTIN_ROLES: dict[str, RoleDefinition] = {
    RoleId.SECURITY.value: RoleDefinition(
        id=RoleId.SECURITY.value,
        name="Security Expert",
        description="Focus on security vulnerabilities, attack vectors, and defensive practices",
        round_1_prefix=(
            "[ROLE: Security Expert]\n"
            "You are acting as a security specialist. Focus your analysis on:\n"
            "- Potential security vulnerabilities (injection, XSS, CSRF, etc.)\n"
            "- Authentication and authorization flaws\n"
            "- Data exposure and privacy risks\n"
            "- Input validation and sanitization\n"
            "- Secure coding practices and defense in depth\n\n"
        ),
        round_2_prefix=(
            "[ROLE: Security Expert - Deliberation]\n"
            "Maintain your security specialist perspective. When reviewing others' answers:\n"
            "- Identify security implications they may have missed\n"
            "- Challenge assumptions about trust boundaries\n"
            "- Propose security hardening for suggested solutions\n\n"
        ),
    ),

    RoleId.PERFORMANCE.value: RoleDefinition(
        id=RoleId.PERFORMANCE.value,
        name="Performance Optimizer",
        description="Focus on performance, scalability, and resource efficiency",
        round_1_prefix=(
            "[ROLE: Performance Optimizer]\n"
            "You are acting as a performance specialist. Focus your analysis on:\n"
            "- Time and space complexity\n"
            "- Database query efficiency and N+1 problems\n"
            "- Memory usage and potential leaks\n"
            "- Caching opportunities\n"
            "- Scalability bottlenecks\n\n"
        ),
        round_2_prefix=(
            "[ROLE: Performance Optimizer - Deliberation]\n"
            "Maintain your performance specialist perspective. When reviewing others' answers:\n"
            "- Analyze performance implications of suggested approaches\n"
            "- Propose optimizations and benchmark considerations\n"
            "- Identify scalability concerns\n\n"
        ),
    ),

    RoleId.SKEPTIC.value: RoleDefinition(
        id=RoleId.SKEPTIC.value,
        name="Skeptic / Devil's Advocate",
        description="Challenge assumptions and find edge cases",
        round_1_prefix=(
            "[ROLE: Skeptic / Devil's Advocate]\n"
            "You are acting as a critical skeptic. Your job is to:\n"
            "- Question assumptions and 'obvious' solutions\n"
            "- Find edge cases and failure modes\n"
            "- Consider what could go wrong\n"
            "- Propose alternative approaches\n"
            "- Play devil's advocate on popular opinions\n\n"
        ),
        round_2_prefix=(
            "[ROLE: Skeptic - Deliberation]\n"
            "Maintain your skeptical perspective. When reviewing others' answers:\n"
            "- Challenge consensus if you see problems\n"
            "- Point out edge cases others missed\n"
            "- Question whether proposed solutions actually work\n\n"
        ),
    ),

    RoleId.ARCHITECT.value: RoleDefinition(
        id=RoleId.ARCHITECT.value,
        name="System Architect",
        description="Focus on system design, patterns, and long-term maintainability",
        round_1_prefix=(
            "[ROLE: System Architect]\n"
            "You are acting as a system architect. Focus your analysis on:\n"
            "- Overall system design and architecture\n"
            "- Design patterns and their appropriate use\n"
            "- Separation of concerns and modularity\n"
            "- API design and contracts\n"
            "- Long-term maintainability and extensibility\n\n"
        ),
        round_2_prefix=(
            "[ROLE: System Architect - Deliberation]\n"
            "Maintain your architectural perspective. When reviewing others' answers:\n"
            "- Evaluate architectural implications\n"
            "- Consider how solutions fit the larger system\n"
            "- Propose structural improvements\n\n"
        ),
    ),

    RoleId.MAINTAINER.value: RoleDefinition(
        id=RoleId.MAINTAINER.value,
        name="Code Maintainer",
        description="Focus on code quality, readability, and maintenance burden",
        round_1_prefix=(
            "[ROLE: Code Maintainer]\n"
            "You are acting as a code maintainer who will live with this code. Focus on:\n"
            "- Code readability and clarity\n"
            "- Documentation and self-documenting code\n"
            "- Test coverage and testability\n"
            "- Error handling and logging\n"
            "- Future maintenance burden\n\n"
        ),
        round_2_prefix=(
            "[ROLE: Code Maintainer - Deliberation]\n"
            "Maintain your maintainer perspective. When reviewing others' answers:\n"
            "- Consider long-term maintenance implications\n"
            "- Evaluate code clarity and documentation needs\n"
            "- Identify potential technical debt\n\n"
        ),
    ),

    RoleId.DX.value: RoleDefinition(
        id=RoleId.DX.value,
        name="Developer Experience",
        description="Focus on API usability, error messages, and developer ergonomics",
        round_1_prefix=(
            "[ROLE: Developer Experience (DX) Advocate]\n"
            "You are acting as a DX advocate. Focus your analysis on:\n"
            "- API usability and intuitiveness\n"
            "- Quality of error messages and debugging experience\n"
            "- Documentation and examples\n"
            "- Developer onboarding friction\n"
            "- Consistency with conventions\n\n"
        ),
        round_2_prefix=(
            "[ROLE: DX Advocate - Deliberation]\n"
            "Maintain your DX perspective. When reviewing others' answers:\n"
            "- Evaluate how solutions affect developer experience\n"
            "- Suggest improvements for usability\n"
            "- Consider the learning curve\n\n"
        ),
    ),

    RoleId.TESTING.value: RoleDefinition(
        id=RoleId.TESTING.value,
        name="Testing Specialist",
        description="Focus on testability, test coverage, and quality assurance",
        round_1_prefix=(
            "[ROLE: Testing Specialist]\n"
            "You are acting as a testing specialist. Focus your analysis on:\n"
            "- Testability of the proposed solution\n"
            "- Unit, integration, and e2e test strategies\n"
            "- Edge cases and boundary conditions\n"
            "- Mocking and test isolation\n"
            "- Test maintenance and reliability\n\n"
        ),
        round_2_prefix=(
            "[ROLE: Testing Specialist - Deliberation]\n"
            "Maintain your testing perspective. When reviewing others' answers:\n"
            "- Identify testing challenges in proposed solutions\n"
            "- Suggest test strategies and coverage gaps\n"
            "- Point out hard-to-test patterns\n\n"
        ),
    ),

    RoleId.NEUTRAL.value: RoleDefinition(
        id=RoleId.NEUTRAL.value,
        name="Neutral",
        description="No specialized perspective - default behavior",
        round_1_prefix="",  # No injection
        round_2_prefix="",  # No injection
    ),
}


# === Built-in Team Presets ===

BUILTIN_TEAMS: dict[str, TeamPreset] = {
    "security_audit": TeamPreset(
        id="security_audit",
        name="Security Audit Team",
        description="Team focused on security review with a skeptic for edge cases",
        assignments={
            "codex": RoleId.SECURITY.value,
            "gemini": RoleId.SKEPTIC.value,
            "opencode": RoleId.ARCHITECT.value,
            "claudeor": RoleId.DX.value,
            "grok": RoleId.TESTING.value,
        },
    ),

    "code_review": TeamPreset(
        id="code_review",
        name="Code Review Team",
        description="Balanced team for thorough code review",
        assignments={
            "codex": RoleId.MAINTAINER.value,
            "gemini": RoleId.PERFORMANCE.value,
            "opencode": RoleId.TESTING.value,
            "claudeor": RoleId.DX.value,
            "grok": RoleId.SKEPTIC.value,
        },
    ),

    "architecture_review": TeamPreset(
        id="architecture_review",
        name="Architecture Review Team",
        description="Team for evaluating system design decisions",
        assignments={
            "codex": RoleId.ARCHITECT.value,
            "gemini": RoleId.PERFORMANCE.value,
            "opencode": RoleId.MAINTAINER.value,
            "claudeor": RoleId.DX.value,
            "grok": RoleId.SKEPTIC.value,
        },
    ),

    "devil_advocate": TeamPreset(
        id="devil_advocate",
        name="Devil's Advocate Team",
        description="All agents act as skeptics to stress-test ideas",
        assignments={
            "codex": RoleId.SKEPTIC.value,
            "gemini": RoleId.SKEPTIC.value,
            "opencode": RoleId.SKEPTIC.value,
            "claudeor": RoleId.SKEPTIC.value,
            "grok": RoleId.SKEPTIC.value,
        },
    ),

    "balanced": TeamPreset(
        id="balanced",
        name="Balanced Review Team",
        description="One each of security, performance, and maintainability",
        assignments={
            "codex": RoleId.SECURITY.value,
            "gemini": RoleId.PERFORMANCE.value,
            "opencode": RoleId.MAINTAINER.value,
            "claudeor": RoleId.DX.value,
            "grok": RoleId.SKEPTIC.value,
        },
    ),

    "optimal": TeamPreset(
        id="optimal",
        name="Optimal Strengths Team",
        description="Roles matched to each model's inherent strengths",
        assignments={
            "codex": RoleId.MAINTAINER.value,      # Deep reasoning for surgical changes
            "gemini": RoleId.ARCHITECT.value,      # Large context for system-wide view
            "opencode": RoleId.DX.value,           # Best tone/steerability for docs
            "claudeor": RoleId.PERFORMANCE.value,  # Fast general-purpose
            "grok": RoleId.SKEPTIC.value,          # Deliberate contrarian, less aligned
        },
    ),
}


# === User Config Loading ===

USER_CONFIG_DIR = Path.home() / ".owlex"
USER_ROLES_FILE = USER_CONFIG_DIR / "roles.json"


def load_user_roles() -> tuple[dict[str, RoleDefinition], dict[str, TeamPreset]]:
    """
    Load user-defined roles and teams from ~/.owlex/roles.json.

    The file format:
    {
        "roles": {
            "my_custom_role": {
                "id": "my_custom_role",
                "name": "My Custom Role",
                "description": "...",
                "round_1_prefix": "...",
                "round_2_prefix": "..."
            }
        },
        "teams": {
            "my_team": {
                "id": "my_team",
                "name": "My Team",
                "description": "...",
                "assignments": {"codex": "security", "gemini": "my_custom_role"}
            }
        }
    }

    Note: The role's "id" field MUST match the dict key. Mismatches are skipped with a warning.
    Invalid entries are skipped individually (per-entry validation) rather than failing the whole file.

    Returns:
        Tuple of (roles_dict, teams_dict)
    """
    if not USER_ROLES_FILE.exists():
        return {}, {}

    try:
        with open(USER_ROLES_FILE) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[WARNING] Failed to parse {USER_ROLES_FILE}: {e}", file=sys.stderr)
        return {}, {}

    # Validate top-level structure
    if not isinstance(data, dict):
        print(f"[WARNING] {USER_ROLES_FILE} must be a JSON object, got {type(data).__name__}", file=sys.stderr)
        return {}, {}

    roles_data = data.get("roles", {})
    if not isinstance(roles_data, dict):
        print(f"[WARNING] 'roles' in {USER_ROLES_FILE} must be an object, got {type(roles_data).__name__}", file=sys.stderr)
        roles_data = {}

    teams_data = data.get("teams", {})
    if not isinstance(teams_data, dict):
        print(f"[WARNING] 'teams' in {USER_ROLES_FILE} must be an object, got {type(teams_data).__name__}", file=sys.stderr)
        teams_data = {}

    roles = {}
    for role_key, role_data in roles_data.items():
        try:
            role = RoleDefinition.from_dict(role_data)
            # Enforce that dict key matches the role's id field
            if role.id != role_key:
                print(
                    f"[WARNING] Role key '{role_key}' does not match id '{role.id}' in {USER_ROLES_FILE}, skipping",
                    file=sys.stderr,
                )
                continue
            roles[role_key] = role
        except (KeyError, TypeError) as e:
            print(f"[WARNING] Invalid role '{role_key}' in {USER_ROLES_FILE}: {e}", file=sys.stderr)
            continue

    teams = {}
    for team_key, team_data in teams_data.items():
        try:
            team = TeamPreset.from_dict(team_data)
            # Enforce that dict key matches the team's id field
            if team.id != team_key:
                print(
                    f"[WARNING] Team key '{team_key}' does not match id '{team.id}' in {USER_ROLES_FILE}, skipping",
                    file=sys.stderr,
                )
                continue
            teams[team_key] = team
        except (KeyError, TypeError) as e:
            print(f"[WARNING] Invalid team '{team_key}' in {USER_ROLES_FILE}: {e}", file=sys.stderr)
            continue

    return roles, teams


def get_merged_roles_and_teams() -> tuple[dict[str, RoleDefinition], dict[str, TeamPreset]]:
    """
    Get merged roles and teams (built-in + user overrides).

    User definitions override built-ins with the same ID.

    Returns:
        Tuple of (merged_roles, merged_teams)
    """
    # Start with built-ins
    roles = dict(BUILTIN_ROLES)
    teams = dict(BUILTIN_TEAMS)

    # Merge user definitions (override built-ins)
    user_roles, user_teams = load_user_roles()
    roles.update(user_roles)
    teams.update(user_teams)

    return roles, teams


# === Role Resolution ===

# Default agent order for auto-assignment
DEFAULT_AGENT_ORDER: Sequence[str] = ("codex", "gemini", "opencode")


class RoleResolver:
    """
    Resolves role specifications to concrete agent->role mappings.

    Resolution priority:
    1. Explicit dict mapping (highest specificity)
    2. List of roles (auto-assigned in agent order)
    3. Team preset name
    4. None (no roles - neutral for all)
    """

    def __init__(
        self,
        roles: dict[str, RoleDefinition],
        teams: dict[str, TeamPreset],
    ):
        self.roles = roles
        self.teams = teams

    def resolve(
        self,
        spec: RoleSpec,
        active_agents: Sequence[str] | None = None,
    ) -> dict[str, RoleDefinition]:
        """
        Resolve a role specification to a mapping of agent -> RoleDefinition.

        Args:
            spec: Role specification (dict, list, team name, or None)
            active_agents: Agents participating in this council (for auto-assign)

        Returns:
            Dict mapping agent name to RoleDefinition

        Raises:
            ValueError: If role or team not found, or invalid spec type
        """
        if active_agents is None:
            active_agents = DEFAULT_AGENT_ORDER

        if spec is None:
            # No roles specified - all agents get neutral
            return {agent: self.roles[RoleId.NEUTRAL.value] for agent in active_agents}

        if isinstance(spec, dict):
            # Mode 1: Explicit mapping {"codex": "security", "gemini": "perf"}
            return self._resolve_explicit_mapping(spec, active_agents)

        if isinstance(spec, list):
            # Mode 2: List auto-assign ["security", "perf", "skeptic"]
            return self._resolve_role_list(spec, active_agents)

        if isinstance(spec, str):
            # Mode 3: Team preset name "security_audit"
            return self._resolve_team_preset(spec, active_agents)

        raise ValueError(f"Invalid role specification type: {type(spec)}")

    def _resolve_explicit_mapping(
        self,
        mapping: dict[str, str],
        active_agents: Sequence[str],
    ) -> dict[str, RoleDefinition]:
        """Resolve explicit agent->role mapping."""
        # Validate for unknown agent keys (typos like "codexx")
        known_agents = {"codex", "gemini", "opencode", "claudeor", "grok"}
        unknown_keys = set(mapping.keys()) - known_agents
        if unknown_keys:
            raise ValueError(f"Unknown agent(s) in role mapping: {', '.join(sorted(unknown_keys))}")

        result = {}
        for agent in active_agents:
            role_id = mapping.get(agent)
            if role_id is None:
                # Agent not in mapping - gets neutral
                result[agent] = self.roles[RoleId.NEUTRAL.value]
            elif role_id not in self.roles:
                raise ValueError(f"Unknown role '{role_id}' for agent '{agent}'")
            else:
                result[agent] = self.roles[role_id]

        return result

    def _resolve_role_list(
        self,
        role_ids: list[str],
        active_agents: Sequence[str],
    ) -> dict[str, RoleDefinition]:
        """Auto-assign roles from list to agents in order."""
        result = {}

        for i, agent in enumerate(active_agents):
            if i < len(role_ids):
                role_id = role_ids[i]
                if role_id not in self.roles:
                    raise ValueError(f"Unknown role '{role_id}' in role list")
                result[agent] = self.roles[role_id]
            else:
                # More agents than roles - remaining get neutral
                result[agent] = self.roles[RoleId.NEUTRAL.value]

        return result

    def _resolve_team_preset(
        self,
        team_id: str,
        active_agents: Sequence[str],
    ) -> dict[str, RoleDefinition]:
        """Resolve team preset to role assignments."""
        if team_id not in self.teams:
            raise ValueError(f"Unknown team preset '{team_id}'")

        team = self.teams[team_id]
        # Team preset is just an explicit mapping under the hood
        return self._resolve_explicit_mapping(team.assignments, active_agents)

    def get_role(self, role_id: str) -> RoleDefinition | None:
        """Get a role definition by ID."""
        return self.roles.get(role_id)

    def get_team(self, team_id: str) -> TeamPreset | None:
        """Get a team preset by ID."""
        return self.teams.get(team_id)

    def list_roles(self) -> list[str]:
        """List all available role IDs."""
        return list(self.roles.keys())

    def list_teams(self) -> list[str]:
        """List all available team preset IDs."""
        return list(self.teams.keys())


# === Global Resolver Instance ===

_resolver: RoleResolver | None = None


def get_resolver() -> RoleResolver:
    """Get the global RoleResolver instance (lazy initialization)."""
    global _resolver
    if _resolver is None:
        _resolver = create_default_resolver()
    return _resolver


def create_default_resolver() -> RoleResolver:
    """Create a RoleResolver with merged built-in and user-defined roles/teams."""
    roles, teams = get_merged_roles_and_teams()
    return RoleResolver(roles=roles, teams=teams)


def reload_resolver():
    """Reload the global resolver (useful after config file changes)."""
    global _resolver
    _resolver = create_default_resolver()
