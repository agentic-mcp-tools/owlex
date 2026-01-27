"""
Council orchestration logic for multi-agent deliberation.
Handles parallel execution and deliberation rounds.
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Any

from .config import config
from .engine import engine, build_agent_response, codex_runner, gemini_runner, opencode_runner
from .prompts import inject_role_prefix, build_deliberation_prompt_with_role
from .roles import RoleSpec, RoleDefinition, RoleResolver, RoleId, get_resolver
from .models import (
    Agent,
    ClaudeOpinion,
    CouncilResponse,
    CouncilRound,
    CouncilMetadata,
)


def _log(msg: str):
    """Log progress to stderr for CLI visibility."""
    print(msg, file=sys.stderr, flush=True)


class Council:
    """
    Orchestrates multi-agent deliberation between Codex, Gemini, and OpenCode.

    The council process:
    1. Round 1: All agents answer the question in parallel
    2. Round 2 (optional): Agents see each other's answers and revise/critique

    Supports specialist roles ("hats") for agents to operate with specific perspectives.
    """

    def __init__(
        self,
        context: Any = None,
        task_engine: Any = None,
        role_resolver: RoleResolver | None = None,
    ):
        """
        Initialize the Council.

        Args:
            context: MCP server context for notifications
            task_engine: Optional TaskEngine instance (uses global engine if not provided).
                        This enables dependency injection for testing.
            role_resolver: Optional RoleResolver instance (uses global resolver if not provided).
        """
        self.context = context
        self._engine = task_engine if task_engine is not None else engine
        self._resolver = role_resolver if role_resolver is not None else get_resolver()
        self.log_entries: list[str] = []

    def log(self, msg: str):
        """Add to log and print to stderr."""
        self.log_entries.append(msg)
        _log(msg)

    async def notify(self, message: str, level: str = "info", progress: float | None = None):
        """Send notification to MCP client if context supports it."""
        if not self.context:
            return
        try:
            session = getattr(self.context, 'session', None)
            if not session:
                return

            # Try progress notification (more visible in Claude Code)
            if hasattr(session, 'send_progress_notification') and progress is not None:
                try:
                    await session.send_progress_notification(
                        progress_token="owlex-council",
                        progress=progress,
                        total=100.0,
                        message=message,
                    )
                except Exception:
                    pass

            # Also send as log message
            if hasattr(session, 'send_log_message'):
                await session.send_log_message(level=level, data=message, logger="owlex")
        except Exception:
            pass

    async def deliberate(
        self,
        prompt: str,
        working_directory: str | None = None,
        claude_opinion: str | None = None,
        deliberate: bool = True,
        critique: bool = True,
        timeout: int | None = None,
        roles: RoleSpec = None,
        team: str | None = None,
    ) -> CouncilResponse:
        """
        Run a council deliberation session.

        Args:
            prompt: The question or task to deliberate on
            working_directory: Working directory context for agents (defaults to CWD)
            claude_opinion: Optional Claude opinion to share with agents
            deliberate: If True, run a second round where agents see each other's answers
            critique: If True, Round 2 asks agents to find flaws instead of revise
            timeout: Timeout per agent in seconds
            roles: Role specification - dict, list, or None (see RoleSpec)
            team: Team preset name (alternative to roles parameter)

        Role specification (mutually exclusive):
            - roles: explicit mapping or auto-assign list
            - team: team preset name
            - Neither: all agents neutral

        Returns:
            CouncilResponse with all rounds and metadata

        Raises:
            ValueError: If both roles and team are specified
        """
        # Validate mutual exclusivity of roles/team (consistent with MCP API)
        if roles is not None and team is not None:
            raise ValueError("Cannot specify both 'roles' and 'team' parameters. Use one or the other.")

        if timeout is None:
            timeout = config.default_timeout
        # timeout=0 means no timeout (wait indefinitely)
        effective_timeout = None if timeout == 0 else timeout

        # Default to CWD if no working_directory provided
        if working_directory is None:
            working_directory = os.getcwd()

        # Determine which agents to run
        excluded = config.council.exclude_agents
        active_agents = [a for a in ["codex", "gemini", "opencode"] if a not in excluded]

        # Resolve roles (team parameter is just a string that resolves to a team preset)
        role_spec = roles if roles is not None else team
        resolved_roles = self._resolver.resolve(role_spec, active_agents)

        council_start = datetime.now()

        # Log and notify role assignments (skip neutral roles)
        role_msgs = [f"{agent.title()}: {role.name}" for agent, role in resolved_roles.items() if role.id != RoleId.NEUTRAL.value]
        if role_msgs:
            roles_summary = ", ".join(role_msgs)
            self.log(f"Roles assigned: {roles_summary}")
            await self.notify(f"Council roles: {roles_summary}", progress=10)

        # === Round 1: Parallel initial queries ===
        if claude_opinion and claude_opinion.strip():
            self.log(f"Claude's opinion received ({len(claude_opinion)} chars)")

        self.log(f"Round 1: querying {', '.join(a.title() for a in active_agents)}...")
        await self.notify(f"Council Round 1: querying {', '.join(a.title() for a in active_agents)}", progress=20)

        round_1 = await self._run_round_1(prompt, working_directory, effective_timeout, resolved_roles)
        await self.notify("Council Round 1 complete", progress=50)

        round_2 = None
        if deliberate:
            await self.notify("Council Round 2: deliberation phase", progress=60)
            round_2 = await self._run_round_2(
                prompt=prompt,
                working_directory=working_directory,
                round_1=round_1,
                claude_opinion=claude_opinion,
                critique=critique,
                timeout=effective_timeout,
                roles=resolved_roles,
            )

        # Build Claude opinion object if provided
        claude_opinion_obj = None
        if claude_opinion and claude_opinion.strip():
            claude_opinion_obj = ClaudeOpinion(
                content=claude_opinion.strip(),
                provided_at=council_start.isoformat(),
            )

        total_duration = (datetime.now() - council_start).total_seconds()
        await self.notify(f"Council deliberation complete ({total_duration:.1f}s)", progress=100)

        return CouncilResponse(
            prompt=prompt,
            working_directory=working_directory,
            deliberation=deliberate,
            critique=critique,
            claude_opinion=claude_opinion_obj,
            round_1=round_1,
            round_2=round_2,
            roles=self._build_role_assignments(resolved_roles),
            metadata=CouncilMetadata(
                total_duration_seconds=(datetime.now() - council_start).total_seconds(),
                rounds=2 if deliberate else 1,
                log=self.log_entries,
            ),
        )

    def _build_role_assignments(
        self,
        resolved_roles: dict[str, RoleDefinition],
    ) -> dict[str, str] | None:
        """Build role assignments dict for response (excludes neutral roles)."""
        assignments = {
            agent: role.id
            for agent, role in resolved_roles.items()
            if role.id != RoleId.NEUTRAL.value
        }
        return assignments if assignments else None

    async def _run_round_1(
        self,
        prompt: str,
        working_directory: str | None,
        timeout: int | None,
        roles: dict[str, RoleDefinition],
    ) -> CouncilRound:
        """Run the first round of parallel queries.

        Option A: R1 uses exec mode (clean start) for all agents.
        Session IDs are captured after completion for use in R2.
        Role prefixes are injected into prompts based on resolved roles.
        """
        round1_start = datetime.now()
        excluded = config.council.exclude_agents

        tasks = {}
        async_tasks = []

        # Create tasks for non-excluded agents
        # All R1 agents use exec mode (clean start) per Option A
        # Role prefixes are injected into prompts
        if "codex" not in excluded:
            codex_role = roles.get("codex")
            codex_prompt = inject_role_prefix(prompt, codex_role)

            codex_task = self._engine.create_task(
                command=f"council_{Agent.CODEX.value}",
                args={"prompt": codex_prompt, "working_directory": working_directory},
                context=self.context,
            )
            tasks["codex"] = codex_task

            # Capture prompt in closure
            _codex_prompt = codex_prompt

            async def run_codex():
                # Clean start for R1 - session ID captured after completion
                await self._engine.run_agent(
                    codex_task, codex_runner, mode="exec",
                    prompt=_codex_prompt, working_directory=working_directory, enable_search=config.codex.enable_search
                )
                elapsed = (datetime.now() - round1_start).total_seconds()
                status = "completed" if codex_task.status == "completed" else "failed"
                self.log(f"Codex {status} ({elapsed:.1f}s)")
                await self.notify(f"Codex {status} ({elapsed:.1f}s)")

            codex_task.async_task = asyncio.create_task(run_codex())
            async_tasks.append(codex_task.async_task)

        if "gemini" not in excluded:
            gemini_role = roles.get("gemini")
            gemini_prompt = inject_role_prefix(prompt, gemini_role)

            gemini_task = self._engine.create_task(
                command=f"council_{Agent.GEMINI.value}",
                args={"prompt": gemini_prompt, "working_directory": working_directory},
                context=self.context,
            )
            tasks["gemini"] = gemini_task

            # Capture prompt in closure
            _gemini_prompt = gemini_prompt

            async def run_gemini():
                # Clean start for R1 - session ID captured after completion
                await self._engine.run_agent(
                    gemini_task, gemini_runner, mode="exec",
                    prompt=_gemini_prompt, working_directory=working_directory
                )
                elapsed = (datetime.now() - round1_start).total_seconds()
                status = "completed" if gemini_task.status == "completed" else "failed"
                self.log(f"Gemini {status} ({elapsed:.1f}s)")
                await self.notify(f"Gemini {status} ({elapsed:.1f}s)")

            gemini_task.async_task = asyncio.create_task(run_gemini())
            async_tasks.append(gemini_task.async_task)

        if "opencode" not in excluded:
            opencode_role = roles.get("opencode")
            opencode_prompt = inject_role_prefix(prompt, opencode_role)

            opencode_task = self._engine.create_task(
                command=f"council_{Agent.OPENCODE.value}",
                args={"prompt": opencode_prompt, "working_directory": working_directory},
                context=self.context,
            )
            tasks["opencode"] = opencode_task

            # Capture prompt in closure
            _opencode_prompt = opencode_prompt

            async def run_opencode():
                # Clean start for R1 - session ID captured after completion
                await self._engine.run_agent(
                    opencode_task, opencode_runner, mode="exec",
                    prompt=_opencode_prompt, working_directory=working_directory
                )
                elapsed = (datetime.now() - round1_start).total_seconds()
                status = "completed" if opencode_task.status == "completed" else "failed"
                self.log(f"OpenCode {status} ({elapsed:.1f}s)")
                await self.notify(f"OpenCode {status} ({elapsed:.1f}s)")

            opencode_task.async_task = asyncio.create_task(run_opencode())
            async_tasks.append(opencode_task.async_task)

        # Wait for all tasks with timeout
        if async_tasks:
            done, pending = await asyncio.wait(
                async_tasks,
                timeout=timeout,
                return_when=asyncio.ALL_COMPLETED
            )

            # Kill subprocesses for any tasks that timed out
            for task in tasks.values():
                if task.async_task in pending:
                    self.log(f"{task.command} timed out")
                    await self._engine.kill_task_subprocess(task)
                    task.status = "failed"
                    task.error = f"Timed out after {timeout} seconds" if timeout else "Timed out"
                    task.completion_time = datetime.now()

        round1_elapsed = (datetime.now() - round1_start).total_seconds()
        self.log(f"Round 1 complete ({round1_elapsed:.1f}s)")

        # Capture session IDs from completed R1 agents for R2 resume
        # Pass since_mtime (R1 start) and working_directory to scope session discovery
        # Subtract 1 second to handle filesystem mtime granularity (some filesystems
        # only store whole seconds, so a session created at 100.9s might have mtime 100)
        r1_start_mtime = round1_start.timestamp() - 1.0

        # Parse session IDs in parallel to reduce inter-round latency
        async def parse_codex_session():
            if "codex" not in tasks or tasks["codex"].status != "completed":
                return None
            session = await codex_runner.parse_session_id(
                "", since_mtime=r1_start_mtime, working_directory=working_directory
            )
            if session and not codex_runner.validate_session_id(session):
                self.log(f"Codex session ID validation failed: {session}")
                return None
            if not session:
                self.log("Codex session ID not found, R2 will use exec mode")
            return session

        async def parse_gemini_session():
            if "gemini" not in tasks or tasks["gemini"].status != "completed":
                return None
            session = await gemini_runner.parse_session_id(
                "", since_mtime=r1_start_mtime, working_directory=working_directory
            )
            if session and not gemini_runner.validate_session_id(session):
                self.log(f"Gemini session ID validation failed: {session}")
                return None
            if not session:
                self.log("Gemini session ID not found, R2 will use exec mode")
            return session

        async def parse_opencode_session():
            if "opencode" not in tasks or tasks["opencode"].status != "completed":
                return None
            session = await opencode_runner.parse_session_id(
                "", since_mtime=r1_start_mtime, working_directory=working_directory
            )
            if session and not opencode_runner.validate_session_id(session):
                self.log(f"OpenCode session ID validation failed: {session}")
                return None
            if not session:
                self.log("OpenCode session ID not found, R2 will use exec mode")
            return session

        codex_session, gemini_session, opencode_session = await asyncio.gather(
            parse_codex_session(),
            parse_gemini_session(),
            parse_opencode_session(),
        )

        return CouncilRound(
            codex=build_agent_response(tasks["codex"], Agent.CODEX, session_id=codex_session) if "codex" in tasks else None,
            gemini=build_agent_response(tasks["gemini"], Agent.GEMINI, session_id=gemini_session) if "gemini" in tasks else None,
            opencode=build_agent_response(tasks["opencode"], Agent.OPENCODE, session_id=opencode_session) if "opencode" in tasks else None,
        )

    async def _run_round_2(
        self,
        prompt: str,
        working_directory: str | None,
        round_1: CouncilRound,
        claude_opinion: str | None,
        critique: bool,
        timeout: int | None,
        roles: dict[str, RoleDefinition],
    ) -> CouncilRound:
        """Run the second round of deliberation.

        Option A: R2 uses explicit session IDs from R1 to resume.
        Falls back to exec mode if session ID is not available.
        Role prefixes are injected (sticky roles) to maintain perspective.
        """
        self.log("Round 2: deliberation phase...")
        excluded = config.council.exclude_agents

        # Get explicit session IDs from R1 (Option A)
        # If session_id is None, we fall back to exec mode
        codex_session = round_1.codex.session_id if round_1.codex else None
        gemini_session = round_1.gemini.session_id if round_1.gemini else None
        opencode_session = round_1.opencode.session_id if round_1.opencode else None

        codex_content = (round_1.codex.content or round_1.codex.error or "(no response)") if round_1.codex else None
        gemini_content = (round_1.gemini.content or round_1.gemini.error or "(no response)") if round_1.gemini else None
        opencode_content = (round_1.opencode.content or round_1.opencode.error or "(no response)") if round_1.opencode else None
        claude_content = claude_opinion.strip() if claude_opinion else None

        round2_start = datetime.now()
        tasks = {}
        async_tasks = []

        # R2 resumes from R1 sessions using explicit session IDs (Option A)
        # Codex: uses resume with explicit session ID from R1
        # Gemini: uses resume with explicit session index from R1
        # OpenCode: uses resume with explicit session ID from R1
        #
        # If session ID is None (R1 failed or parsing failed), fall back to exec mode
        # Role prefixes (sticky roles) are injected to maintain perspective

        if "codex" not in excluded:
            codex_role = roles.get("codex")
            # Build prompt for resume mode (no original needed - agent has R1 context)
            codex_delib_prompt_resume = build_deliberation_prompt_with_role(
                original_prompt=prompt,
                role=codex_role,
                codex_answer=codex_content,
                gemini_answer=gemini_content,
                opencode_answer=opencode_content,
                claude_answer=claude_content,
                critique=critique,
                include_original=False,
            )
            # Build prompt for exec fallback (include original - agent starts fresh)
            codex_delib_prompt_exec = build_deliberation_prompt_with_role(
                original_prompt=prompt,
                role=codex_role,
                codex_answer=codex_content,
                gemini_answer=gemini_content,
                opencode_answer=opencode_content,
                claude_answer=claude_content,
                critique=critique,
                include_original=True,
            )

            codex_delib_task = self._engine.create_task(
                command=f"council_{Agent.CODEX.value}_delib",
                args={"prompt": codex_delib_prompt_resume, "working_directory": working_directory},
                context=self.context,
            )
            tasks["codex"] = codex_delib_task

            # Capture session and prompts in closure
            _codex_session = codex_session
            _codex_delib_prompt_resume = codex_delib_prompt_resume
            _codex_delib_prompt_exec = codex_delib_prompt_exec

            async def run_codex_delib():
                # Resume with explicit session ID if available, otherwise exec with full context
                if _codex_session:
                    await self._engine.run_agent(
                        codex_delib_task, codex_runner, mode="resume",
                        session_ref=_codex_session,
                        prompt=_codex_delib_prompt_resume, working_directory=working_directory,
                        enable_search=config.codex.enable_search
                    )
                else:
                    await self._engine.run_agent(
                        codex_delib_task, codex_runner, mode="exec",
                        prompt=_codex_delib_prompt_exec, working_directory=working_directory,
                        enable_search=config.codex.enable_search
                    )
                elapsed = (datetime.now() - round2_start).total_seconds()
                self.log(f"Codex revised ({elapsed:.1f}s)")
                await self.notify(f"Codex revised ({elapsed:.1f}s)")

            codex_delib_task.async_task = asyncio.create_task(run_codex_delib())
            async_tasks.append(codex_delib_task.async_task)

        if "gemini" not in excluded:
            gemini_role = roles.get("gemini")
            # Build prompt for resume mode (no original needed - agent has R1 context)
            gemini_delib_prompt_resume = build_deliberation_prompt_with_role(
                original_prompt=prompt,
                role=gemini_role,
                codex_answer=codex_content,
                gemini_answer=gemini_content,
                opencode_answer=opencode_content,
                claude_answer=claude_content,
                critique=critique,
                include_original=False,
            )
            # Build prompt for exec fallback (include original - agent starts fresh)
            gemini_delib_prompt_exec = build_deliberation_prompt_with_role(
                original_prompt=prompt,
                role=gemini_role,
                codex_answer=codex_content,
                gemini_answer=gemini_content,
                opencode_answer=opencode_content,
                claude_answer=claude_content,
                critique=critique,
                include_original=True,
            )

            gemini_delib_task = self._engine.create_task(
                command=f"council_{Agent.GEMINI.value}_delib",
                args={"prompt": gemini_delib_prompt_resume, "working_directory": working_directory},
                context=self.context,
            )
            tasks["gemini"] = gemini_delib_task

            # Capture session and prompts in closure
            _gemini_session = gemini_session
            _gemini_delib_prompt_resume = gemini_delib_prompt_resume
            _gemini_delib_prompt_exec = gemini_delib_prompt_exec

            async def run_gemini_delib():
                # Resume with explicit session index if available, otherwise exec with full context
                if _gemini_session:
                    await self._engine.run_agent(
                        gemini_delib_task, gemini_runner, mode="resume",
                        session_ref=_gemini_session,
                        prompt=_gemini_delib_prompt_resume, working_directory=working_directory
                    )
                else:
                    await self._engine.run_agent(
                        gemini_delib_task, gemini_runner, mode="exec",
                        prompt=_gemini_delib_prompt_exec, working_directory=working_directory
                    )
                elapsed = (datetime.now() - round2_start).total_seconds()
                self.log(f"Gemini revised ({elapsed:.1f}s)")
                await self.notify(f"Gemini revised ({elapsed:.1f}s)")

            gemini_delib_task.async_task = asyncio.create_task(run_gemini_delib())
            async_tasks.append(gemini_delib_task.async_task)

        if "opencode" not in excluded:
            opencode_role = roles.get("opencode")
            # Build prompt for resume mode (no original needed - agent has R1 context)
            opencode_delib_prompt_resume = build_deliberation_prompt_with_role(
                original_prompt=prompt,
                role=opencode_role,
                codex_answer=codex_content,
                gemini_answer=gemini_content,
                opencode_answer=opencode_content,
                claude_answer=claude_content,
                critique=critique,
                include_original=False,
            )
            # Build prompt for exec fallback (include original - agent starts fresh)
            opencode_delib_prompt_exec = build_deliberation_prompt_with_role(
                original_prompt=prompt,
                role=opencode_role,
                codex_answer=codex_content,
                gemini_answer=gemini_content,
                opencode_answer=opencode_content,
                claude_answer=claude_content,
                critique=critique,
                include_original=True,
            )

            opencode_delib_task = self._engine.create_task(
                command=f"council_{Agent.OPENCODE.value}_delib",
                args={"prompt": opencode_delib_prompt_resume, "working_directory": working_directory},
                context=self.context,
            )
            tasks["opencode"] = opencode_delib_task

            # Capture session and prompts in closure
            _opencode_session = opencode_session
            _opencode_delib_prompt_resume = opencode_delib_prompt_resume
            _opencode_delib_prompt_exec = opencode_delib_prompt_exec

            async def run_opencode_delib():
                # Resume with explicit session ID if available, otherwise exec with full context
                if _opencode_session:
                    await self._engine.run_agent(
                        opencode_delib_task, opencode_runner, mode="resume",
                        session_ref=_opencode_session,
                        prompt=_opencode_delib_prompt_resume, working_directory=working_directory
                    )
                else:
                    await self._engine.run_agent(
                        opencode_delib_task, opencode_runner, mode="exec",
                        prompt=_opencode_delib_prompt_exec, working_directory=working_directory
                    )
                elapsed = (datetime.now() - round2_start).total_seconds()
                self.log(f"OpenCode revised ({elapsed:.1f}s)")
                await self.notify(f"OpenCode revised ({elapsed:.1f}s)")

            opencode_delib_task.async_task = asyncio.create_task(run_opencode_delib())
            async_tasks.append(opencode_delib_task.async_task)

        # Wait for all tasks with timeout
        if async_tasks:
            done, pending = await asyncio.wait(
                async_tasks,
                timeout=timeout,
                return_when=asyncio.ALL_COMPLETED
            )

            # Kill subprocesses for any tasks that timed out
            for task in tasks.values():
                if task.async_task in pending:
                    self.log(f"{task.command} timed out")
                    await self._engine.kill_task_subprocess(task)
                    task.status = "failed"
                    task.error = f"Timed out after {timeout} seconds" if timeout else "Timed out"
                    task.completion_time = datetime.now()

        round2_elapsed = (datetime.now() - round2_start).total_seconds()
        self.log(f"Round 2 complete ({round2_elapsed:.1f}s)")
        await self.notify("Council Round 2 complete", progress=90)

        return CouncilRound(
            codex=build_agent_response(tasks["codex"], Agent.CODEX) if "codex" in tasks else None,
            gemini=build_agent_response(tasks["gemini"], Agent.GEMINI) if "gemini" in tasks else None,
            opencode=build_agent_response(tasks["opencode"], Agent.OPENCODE) if "opencode" in tasks else None,
        )
