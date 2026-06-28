"""Prompt Segment — structured, hashable, cache-aware prompt building blocks.

Every prompt is assembled from ordered segments. Each segment has:
- segment_id: unique identifier
- segment_type: stable, semi_stable, dynamic, volatile
- content_hash: SHA-256 of canonical content
- token_estimate: rough token count
- provider_cache_relevant: whether this segment contributes to provider-side cache
- redaction_status: whether content has been redacted
- source: origin of the segment content
- created_at: timestamp
- invalidated_by: reason for invalidation if any

Segments are assembled in order: all stable first, then semi_stable, then dynamic, then volatile.
This ordering maximizes provider-side prefix cache hits (DeepSeek, etc.).
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class SegmentType(str, Enum):
    STABLE = "stable"
    SEMI_STABLE = "semi_stable"
    DYNAMIC = "dynamic"
    VOLATILE = "volatile"


@dataclass
class PromptSegment:
    """One segment of a prompt assembly."""

    segment_id: str
    segment_type: SegmentType
    content: str
    source: str = ""
    token_estimate: int = 0
    provider_cache_relevant: bool = True
    redaction_status: str = "none"  # none, redacted, secret_safe
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    invalidated_by: str = ""
    content_hash: str = ""
    can_drop: bool = False
    can_summarize: bool = False
    required_for_completion: bool = False

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]
        if not self.token_estimate:
            self.token_estimate = max(1, len(self.content) // 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "segment_type": self.segment_type.value,
            "content_hash": self.content_hash,
            "token_estimate": self.token_estimate,
            "provider_cache_relevant": self.provider_cache_relevant,
            "redaction_status": self.redaction_status,
            "source": self.source,
            "created_at": self.created_at,
            "invalidated_by": self.invalidated_by,
            "can_drop": self.can_drop,
            "can_summarize": self.can_summarize,
            "required_for_completion": self.required_for_completion,
        }


# ─── Stable prefix segments ──────────────────────────────────────────────────

STABLE_SEGMENT_ORDER: list[str] = [
    "core_system_rules",
    "safety_governor_summary",
    "native_tool_protocol",
    "council_protocol",
    "output_schemas",
    "provider_neutral_rules",
    "project_identity",
]

TYPE_ORDER: dict[str, int] = {
    "stable": 0,
    "semi_stable": 1,
    "dynamic": 2,
    "volatile": 3,
}


def _segment_sort_key(seg: PromptSegment) -> int:
    return TYPE_ORDER.get(seg.segment_type.value, 2)


class PromptAssembly:
    """Builder for assembling prompts from segments with deterministic ordering."""

    def __init__(self, session_id: str = "", goal_hash: str = ""):
        self.segments: list[PromptSegment] = []
        self.session_id = session_id
        self.goal_hash = goal_hash

    def add_segment(self, segment: PromptSegment) -> "PromptAssembly":
        self.segments.append(segment)
        return self

    def add(
        self,
        segment_id: str,
        segment_type: SegmentType,
        content: str,
        source: str = "",
        can_drop: bool = False,
        can_summarize: bool = False,
        required_for_completion: bool = False,
        provider_cache_relevant: bool = True,
        redaction_status: str = "none",
    ) -> "PromptAssembly":
        self.segments.append(
            PromptSegment(
                segment_id=segment_id,
                segment_type=segment_type,
                content=content,
                source=source,
                can_drop=can_drop,
                can_summarize=can_summarize,
                required_for_completion=required_for_completion,
                provider_cache_relevant=provider_cache_relevant,
                redaction_status=redaction_status,
            )
        )
        return self

    def sort(self) -> "PromptAssembly":
        """Sort segments: stable → semi_stable → dynamic → volatile."""
        self.segments.sort(key=_segment_sort_key)
        return self

    def build(self) -> str:
        """Assemble final prompt text. Segments are sorted then concatenated."""
        self.sort()
        parts = []
        for seg in self.segments:
            if seg.invalidated_by:
                continue
            parts.append(seg.content)
        return "\n\n".join(parts)

    def build_messages(
        self, role_content_map: dict[str, str] | None = None
    ) -> list[dict[str, str]]:
        """Build a messages list for provider API.

        Stable/semi_stable segments become the system message.
        Dynamic/volatile segments become user messages.
        """
        self.sort()
        stable_parts: list[str] = []
        dynamic_parts: list[str] = []

        for seg in self.segments:
            if seg.invalidated_by:
                continue
            if seg.segment_type in (SegmentType.STABLE, SegmentType.SEMI_STABLE):
                stable_parts.append(seg.content)
            else:
                dynamic_parts.append(seg.content)

        messages = []
        if stable_parts:
            messages.append({"role": "system", "content": "\n\n".join(stable_parts)})
        if dynamic_parts:
            messages.append({"role": "user", "content": "\n\n".join(dynamic_parts)})
        if role_content_map:
            for role, content in role_content_map.items():
                messages.append({"role": role, "content": content})

        return messages

    def stable_prefix_hash(self) -> str:
        """Hash of only the stable + semi_stable segments."""
        stable_content = []
        for seg in self.segments:
            if seg.invalidated_by:
                continue
            if seg.segment_type in (SegmentType.STABLE, SegmentType.SEMI_STABLE):
                stable_content.append(seg.content_hash)
        raw = "|".join(stable_content)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def full_prompt_hash(self) -> str:
        """Hash of all non-invalidated segments."""
        hashes = [seg.content_hash for seg in self.segments if not seg.invalidated_by]
        raw = "|".join(hashes)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def token_summary(self) -> dict[str, Any]:
        """Token estimates by segment type."""
        summary: dict[str, int] = {
            "stable": 0,
            "semi_stable": 0,
            "dynamic": 0,
            "volatile": 0,
            "total": 0,
        }
        for seg in self.segments:
            if seg.invalidated_by:
                continue
            summary[seg.segment_type.value] += seg.token_estimate
            summary["total"] += seg.token_estimate
        return summary

    def report(self) -> dict[str, Any]:
        """Prompt assembly report for logging/telemetry."""
        summary = self.token_summary()
        return {
            "session_id": self.session_id,
            "goal_hash": self.goal_hash,
            "stable_prefix_hash": self.stable_prefix_hash(),
            "full_prompt_hash": self.full_prompt_hash(),
            "total_tokens": summary["total"],
            "stable_tokens": summary["stable"],
            "semi_stable_tokens": summary["semi_stable"],
            "dynamic_tokens": summary["dynamic"],
            "volatile_tokens": summary["volatile"],
            "cacheable_prefix_tokens": summary["stable"] + summary["semi_stable"],
            "segment_count": len([s for s in self.segments if not s.invalidated_by]),
            "segments": [
                seg.to_dict() for seg in self.segments if not seg.invalidated_by
            ],
        }

    def drop_low_value(self, max_tokens: int | None = None) -> "PromptAssembly":
        """Drop can_drop segments if total exceeds max_tokens.

        Drops volatile can_drop segments first, then dynamic can_drop.
        """
        if max_tokens is None:
            return self
        summary = self.token_summary()
        if summary["total"] <= max_tokens:
            return self
        # Drop volatile can_drop segments first, then dynamic can_drop
        for seg_type in (SegmentType.VOLATILE, SegmentType.DYNAMIC):
            # Sort by token_estimate descending within each type to drop biggest first
            candidates = [
                seg
                for seg in self.segments
                if seg.segment_type == seg_type
                and seg.can_drop
                and not seg.invalidated_by
            ]
            candidates.sort(key=lambda s: s.token_estimate, reverse=True)
            for seg in candidates:
                seg.invalidated_by = "dropped_for_token_budget"
                summary = self.token_summary()
                if summary["total"] <= max_tokens:
                    break
            if summary["total"] <= max_tokens:
                break
        return self

    def summarize_segment(self, segment_id: str, summary_text: str) -> "PromptAssembly":
        """Replace a segment's content with a summarized version."""
        for seg in self.segments:
            if seg.segment_id == segment_id and seg.can_summarize:
                seg.content = summary_text
                seg.content_hash = hashlib.sha256(summary_text.encode()).hexdigest()[
                    :16
                ]
                seg.token_estimate = max(1, len(summary_text) // 4)
                seg.invalidated_by = ""
                break
        return self
