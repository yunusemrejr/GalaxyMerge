"""Prompt Assembly — deterministic, segment-based prompt construction for cache efficiency.

Builds prompts with a stable prefix (reusable across calls) followed by
dynamic middle and volatile tail sections. This structure maximizes
provider-side cache hits (especially DeepSeek-style prefix caching).
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from galaxy_merge.safety.credential_policy import CredentialPolicy


@dataclass
class PromptSegment:
    """A segment of a prompt with metadata for caching and token accounting."""

    segment_id: str
    segment_type: str  # stable, semi_stable, dynamic, volatile
    content: str
    content_hash: str = ""
    token_estimate: int = 0
    provider_cache_relevant: bool = True
    redaction_status: str = "clean"
    source: str = ""
    created_at: float = field(default_factory=time.time)
    invalidated_by: str | None = None

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]
        if not self.token_estimate:
            self.token_estimate = max(1, len(self.content) // 4)


@dataclass
class PromptAssemblyReport:
    """Report on how a prompt was assembled."""

    provider_id: str
    model_id: str
    role: str
    total_estimated_input_tokens: int = 0
    stable_prefix_tokens: int = 0
    dynamic_tokens: int = 0
    volatile_tokens: int = 0
    cache_candidate_tokens: int = 0
    cache_break_reason: str = ""
    reused_segment_ids: list[str] = field(default_factory=list)
    new_segment_ids: list[str] = field(default_factory=list)
    dropped_segment_ids: list[str] = field(default_factory=list)
    compacted_segment_ids: list[str] = field(default_factory=list)
    redacted_segment_ids: list[str] = field(default_factory=list)
    segment_count: int = 0
    assembly_time_ms: int = 0


# Canonical system prompt sections — these should be byte-stable across calls
SYSTEM_CORE = """You are Galaxy Merge Harness, an autonomous coding agent.

Core Rules:
- All mutations must pass through the Native Tool Kernel
- The Safety Governor is deterministic and cannot be overridden by model judgment
- Never commit secrets, credentials, tokens, API keys, or .env files
- Never execute curl|sh or wget|sh patterns
- Never modify the Galaxy Merge codebase itself
- Verify all changes with evidence before claiming completion
- Respect location classifications and deployment policies
- Keep terminal logs, GUI, prompts, memory, and cache free of secrets

Tool Protocol:
- Tools are invoked by name with structured parameters
- Tool results are returned as structured JSON
- Mutating tools require Safety Governor approval
- File paths are relative to WorkRoot unless absolute
- Shell commands are executed in a sandbox with policy enforcement

Output Protocol:
- Respond with valid JSON matching the requested schema
- Include evidence references, not just claims
- Cite specific file paths and line numbers when relevant
- Report confidence levels and open risks
- Never fabricate tool results or verification evidence
"""

SAFETY_SUMMARY = """Safety Governor Summary:
- Blocked paths: /, /bin, /sbin, /usr, /etc, /var, /boot, /dev, /proc, /sys, /run, /root, /home, ~/.ssh, ~/.gnupg, ~/.aws, ~/.config
- Blocked commands: rm -rf /, rm -rf ~, sudo rm, chmod 777, dd if=, mkfs, mount, curl|sh, wget|sh
- Credential files blocked: .env, .npmrc (with token), .pypirc, SSH keys, cloud credentials
- Self-protection: Galaxy Merge codebase is read-only when launched from within it
- Redaction: API keys, tokens, cookies, and credentials are redacted from all outputs
"""

# Singleton instances of stable segments (computed once per session)
_stable_segment_cache: dict[str, PromptSegment] = {}


class PromptBuilder:
    """Deterministic prompt builder with segment-level caching and token accounting."""

    def __init__(self, gm_dir: Path, provider_id: str = "", model_id: str = ""):
        self.gm_dir = gm_dir
        self.provider_id = provider_id
        self.model_id = model_id
        self.redactor = CredentialPolicy(
            gm_dir.parent if gm_dir.name == ".gm" else gm_dir
        )
        self._segments: list[PromptSegment] = []
        self._start_time = time.monotonic()

    def add_stable_system(self) -> "PromptBuilder":
        """Add the immutable core system prompt."""
        seg = PromptSegment(
            segment_id="system_core",
            segment_type="stable",
            content=SYSTEM_CORE,
            source="hardcoded",
            provider_cache_relevant=True,
        )
        self._segments.append(seg)
        return self

    def add_safety_summary(self) -> "PromptBuilder":
        """Add the safety governor summary (stable across sessions with same policy)."""
        seg = PromptSegment(
            segment_id="safety_summary",
            segment_type="stable",
            content=SAFETY_SUMMARY,
            source="hardcoded",
            provider_cache_relevant=True,
        )
        self._segments.append(seg)
        return self

    def add_tool_schemas(self, tool_schemas: list[dict[str, Any]]) -> "PromptBuilder":
        """Add tool schemas in deterministic order."""
        # Sort by name for stable ordering
        sorted_schemas = sorted(tool_schemas, key=lambda s: s.get("name", ""))
        content = "Available Tools:\n"
        for schema in sorted_schemas:
            content += f"\nTool: {schema.get('name', 'unknown')}\n"
            content += f"Description: {schema.get('description', '')}\n"
            content += f"Mutates: {schema.get('mutates', False)}\n"
            params = schema.get("parameters", {})
            if params:
                content += (
                    f"Parameters: {json.dumps(params, sort_keys=True, indent=2)}\n"
                )

        seg = PromptSegment(
            segment_id="tool_schemas",
            segment_type="stable",
            content=content,
            source="tool_kernel",
            provider_cache_relevant=True,
        )
        self._segments.append(seg)
        return self

    def add_role_instructions(
        self, role: str, role_definition: dict[str, Any], output_schema: dict[str, Any]
    ) -> "PromptBuilder":
        """Add role-specific instructions (stable for a given role)."""
        instructions = role_definition.get("instructions", [])
        purpose = role_definition.get("purpose", "")

        content = f"You are the {role} role in Galaxy Merge Harness.\n"
        content += f"Purpose: {purpose}\n\n"
        content += "Instructions:\n"
        for instr in sorted(instructions):  # Sort for stability
            content += f"- {instr}\n"

        if output_schema:
            content += f"\nOutput Schema:\n{json.dumps(output_schema, sort_keys=True, indent=2)}\n"

        content += "\nRespond with valid JSON matching the schema.\n"

        seg = PromptSegment(
            segment_id=f"role_{role}",
            segment_type="stable",
            content=content,
            source=f"role_definition:{role}",
            provider_cache_relevant=True,
        )
        self._segments.append(seg)
        return self

    def add_project_identity(
        self, workroot: str, project_name: str, language_hints: list[str]
    ) -> "PromptBuilder":
        """Add project identity block (semi-stable — changes only when project config changes)."""
        content = f"Project: {project_name}\n"
        content += f"WorkRoot: {workroot}\n"
        if language_hints:
            content += f"Languages/Frameworks: {', '.join(sorted(language_hints))}\n"

        seg = PromptSegment(
            segment_id="project_identity",
            segment_type="semi_stable",
            content=content,
            source="project_config",
            provider_cache_relevant=True,
        )
        self._segments.append(seg)
        return self

    def add_goal(self, goal: str, completion_criteria: list[str]) -> "PromptBuilder":
        """Add the current goal (dynamic — changes per task)."""
        content = f"Goal: {goal}\n"
        if completion_criteria:
            content += "Completion Criteria:\n"
            for i, c in enumerate(sorted(completion_criteria), 1):
                content += f"{i}. {c}\n"

        seg = PromptSegment(
            segment_id="goal",
            segment_type="dynamic",
            content=content,
            source="user_input",
            provider_cache_relevant=False,
        )
        self._segments.append(seg)
        return self

    def add_current_plan(self, plan: dict[str, Any]) -> "PromptBuilder":
        """Add current plan (dynamic)."""
        content = f"Current Plan:\n{json.dumps(plan, sort_keys=True, indent=2)}\n"
        seg = PromptSegment(
            segment_id="current_plan",
            segment_type="dynamic",
            content=content,
            source="planner",
            provider_cache_relevant=False,
        )
        self._segments.append(seg)
        return self

    def add_file_evidence(
        self, path: str, content: str, line_range: tuple[int, int] | None = None
    ) -> "PromptBuilder":
        """Add file evidence (dynamic — only relevant excerpts)."""
        if line_range:
            content = (
                f"File: {path} (lines {line_range[0]}-{line_range[1]}):\n{content}\n"
            )
        else:
            content = f"File: {path}:\n{content}\n"

        seg = PromptSegment(
            segment_id=f"file_{hashlib.sha256(path.encode()).hexdigest()[:8]}",
            segment_type="dynamic",
            content=content,
            source=f"file:{path}",
            provider_cache_relevant=False,
        )
        self._segments.append(seg)
        return self

    def add_tool_results(self, results: list[dict[str, Any]]) -> "PromptBuilder":
        """Add tool execution results (volatile — changes every step)."""
        content = "Tool Results:\n"
        for r in results:
            tool = r.get("tool", "unknown")
            status = r.get("status", r.get("success", "unknown"))
            content += f"- {tool}: {status}\n"
            data = r.get("data", {})
            if data:
                content += f"  Data: {json.dumps(data, sort_keys=True, default=str)[:500]}...\n"

        seg = PromptSegment(
            segment_id="tool_results",
            segment_type="volatile",
            content=content,
            source="tool_kernel",
            provider_cache_relevant=False,
        )
        self._segments.append(seg)
        return self

    def add_browser_evidence(
        self, console_errors: list[str], network_failures: list[str]
    ) -> "PromptBuilder":
        """Add browser evidence (volatile)."""
        content = "Browser Evidence:\n"
        if console_errors:
            # Group identical errors
            error_counts: dict[str, int] = {}
            for e in console_errors:
                error_counts[e] = error_counts.get(e, 0) + 1
            content += "Console Errors:\n"
            for err, count in sorted(error_counts.items()):
                suffix = f" (x{count})" if count > 1 else ""
                content += f"- {err[:200]}{suffix}\n"
        if network_failures:
            content += "Network Failures:\n"
            for f in network_failures[:20]:  # Cap
                content += f"- {f[:200]}\n"

        seg = PromptSegment(
            segment_id="browser_evidence",
            segment_type="volatile",
            content=content,
            source="browser_manager",
            provider_cache_relevant=False,
        )
        self._segments.append(seg)
        return self

    def add_council_outputs(self, council_results: dict[str, Any]) -> "PromptBuilder":
        """Add council role outputs (semi-stable — summarized, not raw)."""
        content = "Council Findings:\n"
        for role, outputs in sorted(council_results.items()):
            if isinstance(outputs, list):
                for out in outputs:
                    if isinstance(out, dict):
                        parsed = out.get("parsed", {})
                        content += f"\n[{role.upper()}]\n"
                        # Only include key structured fields, not raw prose
                        for key in sorted(parsed.keys()):
                            val = parsed[key]
                            if isinstance(val, str) and len(val) > 500:
                                val = val[:500] + "..."
                            content += f"  {key}: {val}\n"
                    elif isinstance(out, str):
                        content += f"\n[{role.upper()}] {out[:500]}\n"

        seg = PromptSegment(
            segment_id="council_outputs",
            segment_type="dynamic",
            content=content,
            source="fusion_council",
            provider_cache_relevant=False,
        )
        self._segments.append(seg)
        return self

    def add_question(self, question: str) -> "PromptBuilder":
        """Add the specific question for this role (volatile tail)."""
        seg = PromptSegment(
            segment_id="question",
            segment_type="volatile",
            content=f"Question: {question}\n",
            source="role_request",
            provider_cache_relevant=False,
        )
        self._segments.append(seg)
        return self

    def build(self, role: str = "") -> tuple[str, PromptAssemblyReport]:
        """Build the final prompt string and assembly report.

        Segments are ordered: stable → semi_stable → dynamic → volatile.
        This ordering maximizes provider-side prefix cache hits.
        """
        # Sort segments by type priority
        type_priority = {"stable": 0, "semi_stable": 1, "dynamic": 2, "volatile": 3}
        sorted_segments = sorted(
            self._segments,
            key=lambda s: (type_priority.get(s.segment_type, 9), s.segment_id),
        )

        # Build messages list
        messages: list[dict[str, str]] = []
        stable_content = ""
        dynamic_content = ""
        volatile_content = ""

        for seg in sorted_segments:
            if seg.segment_type == "stable":
                stable_content += seg.content
            elif seg.segment_type == "semi_stable":
                stable_content += (
                    seg.content
                )  # Semi-stable is close to stable for cache purposes
            elif seg.segment_type == "dynamic":
                dynamic_content += seg.content + "\n"
            else:
                volatile_content += seg.content + "\n"

        # Construct messages
        if stable_content:
            messages.append({"role": "system", "content": stable_content})
        if dynamic_content:
            messages.append({"role": "user", "content": dynamic_content.strip()})
        if volatile_content:
            # Append volatile content to the last user message or create new one
            if messages and messages[-1]["role"] == "user":
                messages[-1]["content"] += "\n" + volatile_content.strip()
            else:
                messages.append({"role": "user", "content": volatile_content.strip()})

        # Compute metrics
        stable_tokens = sum(
            s.token_estimate
            for s in sorted_segments
            if s.segment_type in ("stable", "semi_stable")
        )
        dynamic_tokens = sum(
            s.token_estimate for s in sorted_segments if s.segment_type == "dynamic"
        )
        volatile_tokens = sum(
            s.token_estimate for s in sorted_segments if s.segment_type == "volatile"
        )
        total_tokens = stable_tokens + dynamic_tokens + volatile_tokens

        report = PromptAssemblyReport(
            provider_id=self.provider_id,
            model_id=self.model_id,
            role=role,
            total_estimated_input_tokens=total_tokens,
            stable_prefix_tokens=stable_tokens,
            dynamic_tokens=dynamic_tokens,
            volatile_tokens=volatile_tokens,
            cache_candidate_tokens=stable_tokens,
            segment_count=len(sorted_segments),
            reused_segment_ids=[
                s.segment_id
                for s in sorted_segments
                if s.segment_type in ("stable", "semi_stable")
            ],
            new_segment_ids=[
                s.segment_id for s in sorted_segments if s.segment_type == "dynamic"
            ],
            assembly_time_ms=int((time.monotonic() - self._start_time) * 1000),
        )

        return json.dumps(messages, ensure_ascii=False), report

    def get_messages(self) -> list[dict[str, str]]:
        """Get the prompt as a messages list (for provider API compatibility)."""
        prompt_str, _ = self.build()
        return json.loads(prompt_str) if prompt_str else []

    def reset(self) -> "PromptBuilder":
        """Reset the builder for a new prompt."""
        self._segments = []
        self._start_time = time.monotonic()
        return self


def build_stable_prefix(
    tool_schemas: list[dict[str, Any]],
    role: str,
    role_definition: dict[str, Any],
    output_schema: dict[str, Any],
) -> list[dict[str, str]]:
    """Build a stable prefix for a specific role. Used by council for cache efficiency.

    This is a lightweight builder that produces only the stable portion.
    """
    builder = PromptBuilder(Path("/tmp"))  # Dummy path, not used for stable content
    builder.add_stable_system()
    builder.add_safety_summary()
    builder.add_tool_schemas(tool_schemas)
    builder.add_role_instructions(role, role_definition, output_schema)
    return builder.get_messages()
