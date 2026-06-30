import json
import re
from typing import Any, Final

from galaxy_merge.fusion.schemas import ROLE_SCHEMAS

EVIDENCE_RANKING: list[str] = [
    "direct_file_content",
    "test_output",
    "build_output",
    "git_diff",
    "tool_logs",
    "multiple_model_findings",
    "single_model_claim",
    "unsupported_assumption",
]

CORE_PERSPECTIVES: Final[tuple[str, ...]] = (
    "planner",
    "implementer",
    "reviewer",
    "skeptic",
)


def validate_schema(role: str, parsed: dict[str, Any]) -> list[str]:
    errors = []
    schema = ROLE_SCHEMAS.get(role)
    if not schema:
        return []
    required = schema.get("required", [])
    for field in required:
        if field not in parsed:
            errors.append(f"missing required field: {field}")
    return errors


def repair_malformed(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if len(lines) >= 2:
            content = "\n".join(lines[1:])
        if content.endswith("```"):
            content = content[:-3].strip()
    content = re.sub(r",\s*([}\]])", r"\1", content)
    content = re.sub(r"(['\"])\s*['\"]\s*:", r"\1:", content)
    return content.strip()


class Synthesizer:
    def fuse(self, council_results: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        all_findings: list[dict[str, Any]] = []
        all_risks: list[str] = []
        all_changes: list[dict[str, Any]] = []
        contradictions: list[dict[str, Any]] = []
        errors: list[str] = []
        schema_errors: list[str] = []
        successful_roles: set[str] = set()
        failed_roles: set[str] = set()

        for role, results in council_results.items():
            for result in results:
                if "error" in result:
                    errors.append(f"[{role}] {result['error']}")
                    failed_roles.add(role)
                    continue

                successful_roles.add(role)
                parsed = result.get("parsed", {})
                ve = validate_schema(role, parsed)
                if ve:
                    schema_errors.extend([f"[{role}] {e}" for e in ve])

                if role == "planner":
                    for step in parsed.get("steps", []):
                        all_findings.append(
                            {
                                "type": "step",
                                "content": step,
                                "source": role,
                                "evidence": parsed.get("goal_understanding", ""),
                            }
                        )
                    for f in parsed.get("relevant_files", []):
                        all_findings.append(
                            {"type": "file", "content": f, "source": role}
                        )

                elif role == "scout":
                    for f in parsed.get("files_found", []):
                        all_findings.append(
                            {
                                "type": "file",
                                "content": f,
                                "source": role,
                                "evidence": "tool_logs",
                            }
                        )
                    if parsed.get("architecture_summary"):
                        all_findings.append(
                            {
                                "type": "architecture",
                                "content": parsed["architecture_summary"],
                                "source": role,
                            }
                        )

                elif role == "implementer":
                    for change in parsed.get("changes", []):
                        all_changes.append(change)
                        all_findings.append(
                            {
                                "type": "change",
                                "content": f"{change.get('action', '')}: {change.get('file', '')}",
                                "source": role,
                                "rationale": change.get("rationale", ""),
                            }
                        )

                elif role == "reviewer":
                    for finding in parsed.get("findings", []):
                        all_findings.append(
                            {
                                **finding,
                                "source": role,
                                "type": finding.get("type", "finding"),
                            }
                        )
                    all_risks.extend(parsed.get("risks", []))

                elif role == "skeptic":
                    if not parsed.get("completion_claim_valid", True):
                        for blocker in parsed.get("blockers", []):
                            contradictions.append(
                                {
                                    "type": "blocker",
                                    "description": blocker,
                                    "source": role,
                                }
                            )

        deduplicated = self._deduplicate(all_findings)
        evidence_scored = self._score_by_evidence(deduplicated)
        resolved = self._resolve_contradictions(contradictions, all_changes)
        missing_perspectives = self._missing_perspectives(
            successful_roles, failed_roles
        )
        confidence = self._completion_confidence(
            missing_perspectives, errors, schema_errors
        )

        return {
            "plan": self._build_plan(all_changes, evidence_scored),
            "summary": self._build_summary(
                all_changes,
                errors,
                resolved,
                schema_errors,
                missing_perspectives,
            ),
            "findings": evidence_scored,
            "risks": all_risks,
            "errors": errors,
            "schema_errors": schema_errors,
            "missing_perspectives": missing_perspectives,
            "council_degraded": bool(missing_perspectives or errors or schema_errors),
            "completion_confidence": confidence,
            "contradictions_resolved": resolved,
            "changes_proposed": len(all_changes),
        }

    def validate_and_repair(self, role: str, content: str) -> dict[str, Any]:
        repaired = repair_malformed(content)
        try:
            parsed = json.loads(repaired)
            return {
                "valid": True,
                "parsed": parsed,
                "was_repaired": repaired != content,
            }
        except json.JSONDecodeError as e:
            return {
                "valid": False,
                "parsed": {"raw": content},
                "error": str(e),
                "was_repaired": False,
            }

    def _deduplicate(self, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen = set()
        unique = []
        for f in findings:
            key = str(f.get("evidence", f.get("content", f.get("file", ""))))
            if key not in seen:
                seen.add(key)
                unique.append(f)
        return unique

    def _score_by_evidence(
        self, findings: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        scored = []
        for f in findings:
            evidence = f.get("evidence", "")
            if evidence == "direct_file_content" or evidence == "tool_logs":
                f["confidence"] = 0.9
            elif evidence == "git_diff" or evidence == "test_output":
                f["confidence"] = 0.8
            elif evidence == "multiple_model_findings":
                f["confidence"] = 0.7
            elif evidence == "single_model_claim":
                f["confidence"] = 0.4
            else:
                f["confidence"] = 0.3
            scored.append(f)
        return sorted(scored, key=lambda x: x.get("confidence", 0), reverse=True)

    def _missing_perspectives(
        self, successful_roles: set[str], failed_roles: set[str]
    ) -> list[str]:
        missing = [role for role in CORE_PERSPECTIVES if role not in successful_roles]
        for role in sorted(failed_roles):
            if role not in missing:
                missing.append(role)
        return missing

    def _completion_confidence(
        self,
        missing_perspectives: list[str],
        errors: list[str],
        schema_errors: list[str],
    ) -> float:
        if not missing_perspectives and not errors and not schema_errors:
            return 1.0
        penalty = 0.25 * len(missing_perspectives)
        penalty += 0.05 * max(0, len(errors) - len(missing_perspectives))
        penalty += 0.1 * len(schema_errors)
        return round(max(0.0, 1.0 - penalty), 2)

    def _resolve_contradictions(
        self, contradictions: list[dict[str, Any]], changes: list[dict[str, Any]]
    ) -> list[str]:
        import re

        resolved = []
        for c in contradictions:
            if c.get("type") == "blocker":
                description = c.get("description", "")
                desc_words = set(re.findall(r"\w+", description.lower()))
                matched = []
                for ch in changes:
                    ch_text = str(ch).lower()
                    ch_words = set(re.findall(r"\w+", ch_text))
                    overlap = desc_words & ch_words
                    if len(overlap) >= 1:
                        matched.append(ch.get("file", ""))
                if matched:
                    resolved.append(
                        f"blocker '{description}' addressed by changes to {', '.join(matched)}"
                    )
                else:
                    resolved.append(f"unresolved blocker: {description}")
        return resolved

    def _build_plan(
        self, changes: list[dict[str, Any]], findings: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        plan = []
        file_order = []
        seen_files = set()
        for change in changes:
            file_path = change.get("file", "")
            if file_path and file_path not in seen_files:
                seen_files.add(file_path)
                file_order.append(file_path)
        for f in findings:
            file_path = f.get("file", "")
            if file_path and file_path not in seen_files:
                seen_files.add(file_path)
                file_order.append(file_path)

        for fp in file_order:
            matching_changes = [c for c in changes if c.get("file") == fp]
            if matching_changes:
                for c in matching_changes:
                    action = c.get("action", "edit")
                    diff_content = c.get("diff", "")
                    if action == "delete":
                        plan.append(
                            {
                                "tool": "file.delete",
                                "params": {"path": c.get("file", "")},
                                "rationale": c.get("rationale", ""),
                            }
                        )
                    elif diff_content and action in ("edit", "create"):
                        plan.append(
                            {
                                "tool": "file.write",
                                "params": {
                                    "path": c.get("file", ""),
                                    "content": diff_content,
                                },
                                "rationale": c.get("rationale", ""),
                            }
                        )
                    else:
                        plan.append(
                            {
                                "tool": "file.read",
                                "params": {"path": c.get("file", "")},
                                "rationale": c.get("rationale", "")
                                or "inspect file for changes",
                            }
                        )
            else:
                plan.append(
                    {
                        "tool": "file.read",
                        "params": {"path": fp},
                        "rationale": "inspect relevant file",
                    }
                )
        return plan

    def _build_summary(
        self,
        changes: list[dict[str, Any]],
        errors: list[str],
        resolved: list[str],
        schema_errors: list[str],
        missing_perspectives: list[str],
    ) -> str:
        parts = []
        if changes:
            files = ", ".join(sorted(set(c.get("file", "") for c in changes)))
            parts.append(f"Changes to: {files}")
        if missing_perspectives:
            parts.append(f"Missing perspectives: {', '.join(missing_perspectives)}")
        if errors:
            parts.append(f"Errors: {'; '.join(errors[:3])}")
        if schema_errors:
            parts.append(f"Schema issues: {'; '.join(schema_errors[:3])}")
        if resolved:
            blockers = [r for r in resolved if "unresolved" in r]
            if blockers:
                parts.append(f"Blockers: {'; '.join(blockers)}")
        return " | ".join(parts) if parts else "No changes proposed"
