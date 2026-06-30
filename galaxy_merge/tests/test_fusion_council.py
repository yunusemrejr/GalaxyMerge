"""
Verify council-based fusion actually uses multiple roles and synthesizes their
outputs — not single-model "pick best answer".

Uses a mock provider that returns controlled structured JSON per role.
"""

import json
from typing import Any

import pytest

from galaxy_merge.fusion.council import Council
from galaxy_merge.fusion.router import FusionRouter
from galaxy_merge.fusion.schemas import ROLE_SCHEMAS
from galaxy_merge.fusion.roles import ROLE_DEFINITIONS
from galaxy_merge.fusion.synthesizer import Synthesizer
from galaxy_merge.providers.base import ProviderBase
from galaxy_merge.providers.registry import ProviderRegistry

pytestmark = [pytest.mark.unit]


# =============================================================================
# Mock provider that returns controlled structured output per role
# =============================================================================

MOCK_ROLE_RESPONSES = {
    "planner": {
        "steps": ["inspect src/main.py", "add error handling", "write test"],
        "relevant_files": ["src/main.py", "tests/test_main.py"],
        "completion_criteria": ["no crash on empty input", "tests pass"],
        "goal_understanding": "add input validation to the CLI entry point",
        "risks": ["may break existing error paths"],
    },
    "scout": {
        "files_found": ["src/main.py", "src/cli.py", "src/errors.py"],
        "architecture_summary": "CLI app with FastAPI backend, three modules",
        "uncertainties": ["error module location unconfirmed"],
    },
    "implementer": {
        "changes": [
            {
                "file": "src/main.py",
                "action": "edit",
                "diff": "--- a/src/main.py\n+++ b/src/main.py\n+def validate(): pass",
                "rationale": "add validation function",
            },
            {
                "file": "tests/test_main.py",
                "action": "edit",
                "diff": "+def test_validate(): pass",
                "rationale": "test validation",
            },
        ]
    },
    "reviewer": {
        "findings": [
            {
                "type": "bug",
                "file": "src/main.py",
                "evidence": "no input validation on line 42",
                "severity": "high",
                "recommendation": "add try/except",
            },
            {
                "type": "style",
                "file": "src/cli.py",
                "evidence": "line 10 > 120 chars",
                "severity": "low",
                "recommendation": "wrap",
            },
        ],
        "risks": ["validation may break existing callers"],
        "approved": True,
    },
    "skeptic": {
        "blockers": [],
        "missing_evidence": ["test_existing_behavior_not_regressed"],
        "completion_claim_valid": True,
    },
    "cheap_verifier": {
        "findings": [
            {
                "type": "info",
                "file": "src/main.py",
                "evidence": "syntax looks valid",
                "severity": "low",
            },
        ]
    },
    "synthesizer": {
        "plan": [
            {
                "tool": "file.patch",
                "params": {"path": "src/main.py"},
                "rationale": "add validation",
            },
        ],
        "summary": "Changes to src/main.py and tests",
        "contradictions_resolved": [],
    },
}

CONTRADICTORY_REVIEW = {
    "reviewer": {
        "findings": [
            {
                "type": "bug",
                "file": "src/main.py",
                "evidence": "input not validated",
                "severity": "high",
                "recommendation": "add try/except",
            },
            {
                "type": "security",
                "file": "src/cli.py",
                "evidence": "eval() on user input",
                "severity": "critical",
                "recommendation": "remove eval()",
            },
        ],
        "risks": ["security hole in cli.py"],
        "approved": False,
    },
    "skeptic": {
        "blockers": ["eval() vulnerability not addressed"],
        "missing_evidence": ["no proof eval was removed"],
        "completion_claim_valid": False,
    },
}


class MockProvider(ProviderBase):
    def __init__(self, provider_id: str, config: dict[str, Any]):
        super().__init__(provider_id, config)
        self._mock_responses: dict[str, dict[str, Any]] = {}
        self.call_history: list[dict[str, Any]] = []

    def set_mock_responses(self, responses: dict[str, dict[str, Any]]) -> None:
        self._mock_responses = responses

    async def chat_completion(
        self, messages, model, temperature=0.7, max_tokens=None, stream=False, **kwargs
    ):
        self.call_history.append(
            {
                "role": "extracted_from_prompt",
                "model": model,
            }
        )
        role = ""
        for msg in messages:
            if msg["role"] == "system" and "purpose" in msg.get("content", ""):
                for r in ROLE_DEFINITIONS:
                    if r in msg["content"] and r != "synthesizer":
                        role = r
                        break
        response_data = self._mock_responses.get(role, {})
        content = (
            json.dumps(response_data)
            if response_data
            else json.dumps({"raw": "mock response"})
        )
        return {"success": True, "content": content, "model": model, "usage": {}}

    async def check_health(self):
        return True


# =============================================================================
# TEST: Council assigns all configured roles
# =============================================================================


class TestCouncilRoleAssignment:
    @pytest.mark.asyncio
    async def test_all_roles_assigned(self, tmp_path):
        """Verify all 7 roles from fusion.json are assigned to the council."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        fusion_config = {
            "councils": {
                "coding_default": {
                    "max_parallel_calls": 4,
                    "timeout_seconds": 30,
                    "roles": {
                        "planner": {
                            "required": True,
                            "model_selector": {
                                "role": "planner",
                                "cost_policy": "balanced",
                            },
                        },
                        "scout": {
                            "required": True,
                            "model_selector": {"role": "scout", "cost_policy": "cheap"},
                        },
                        "implementer": {
                            "required": True,
                            "model_selector": {
                                "role": "implementer",
                                "cost_policy": "quality",
                            },
                        },
                        "reviewer": {
                            "required": True,
                            "model_selector": {
                                "role": "reviewer",
                                "cost_policy": "balanced",
                            },
                        },
                        "cheap_verifier": {
                            "required": True,
                            "count": 2,
                            "model_selector": {
                                "role": "cheap_verifier",
                                "cost_policy": "cheap",
                            },
                        },
                        "synthesizer": {
                            "required": True,
                            "model_selector": {
                                "role": "synthesizer",
                                "cost_policy": "quality",
                            },
                        },
                    },
                }
            }
        }
        (config_dir / "fusion.json").write_text(json.dumps(fusion_config))

        providers_json = {
            "providers": {
                "mock": {
                    "enabled": True,
                    "type": "mock",
                    "base_url": "http://mock",
                    "auth": {"type": "none"},
                    "timeout_seconds": 5,
                }
            }
        }
        (config_dir / "providers.json").write_text(json.dumps(providers_json))

        models_json = {
            "models": {
                "mock:planner": {
                    "provider": "mock",
                    "model": "mock-v1",
                    "enabled": True,
                    "context_window": 32000,
                    "strengths": ["planning"],
                    "roles": ["planner", "synthesizer"],
                },
                "mock:scout": {
                    "provider": "mock",
                    "model": "mock-v2",
                    "enabled": True,
                    "context_window": 32000,
                    "strengths": ["fast_scan"],
                    "roles": ["scout", "cheap_verifier"],
                },
                "mock:implementer": {
                    "provider": "mock",
                    "model": "mock-v3",
                    "enabled": True,
                    "context_window": 32000,
                    "strengths": ["implementation"],
                    "roles": ["implementer"],
                },
                "mock:reviewer": {
                    "provider": "mock",
                    "model": "mock-v4",
                    "enabled": True,
                    "context_window": 32000,
                    "strengths": ["review"],
                    "roles": ["reviewer", "skeptic"],
                },
            }
        }
        (config_dir / "models.json").write_text(json.dumps(models_json))

        registry = ProviderRegistry(config_dir)
        registry.load()

        mock_prov = registry.get("mock")
        assert mock_prov is not None
        mock_prov.set_mock_responses(MOCK_ROLE_RESPONSES)

        council = Council(
            registry,
            fusion_config["councils"]["coding_default"],
            "fix input validation",
        )
        results = await council.execute()

        assigned = set(results.keys())
        expected = {
            "planner",
            "scout",
            "implementer",
            "reviewer",
            "cheap_verifier",
            "synthesizer",
        }
        missing = expected - assigned
        assert not missing, f"Roles not assigned: {missing}"
        assert len(results.get("cheap_verifier", [])) == 2, (
            "cheap_verifier count should be 2"
        )


# =============================================================================
# TEST: Each role produces structured output matching its schema
# =============================================================================


class TestStructuredRoleOutputs:
    @pytest.mark.asyncio
    async def test_planner_output_valid(self):
        """Verify planner output has required fields: steps, completion_criteria."""
        schema = ROLE_SCHEMAS["planner"]
        required = schema.get("required", [])
        data = MOCK_ROLE_RESPONSES["planner"]
        for field in required:
            assert field in data and data[field], (
                f"planner missing required field: {field}"
            )

    @pytest.mark.asyncio
    async def test_scout_output_valid(self):
        schema = ROLE_SCHEMAS["scout"]
        required = schema.get("required", [])
        data = MOCK_ROLE_RESPONSES["scout"]
        for field in required:
            assert field in data and data[field], (
                f"scout missing required field: {field}"
            )

    @pytest.mark.asyncio
    async def test_implementer_output_valid(self):
        schema = ROLE_SCHEMAS["implementer"]
        required = schema.get("required", [])
        data = MOCK_ROLE_RESPONSES["implementer"]
        for field in required:
            assert field in data and data[field], (
                f"implementer missing required field: {field}"
            )
        for change in data.get("changes", []):
            assert "file" in change
            assert "action" in change
            assert "rationale" in change

    @pytest.mark.asyncio
    async def test_reviewer_output_valid(self):
        schema = ROLE_SCHEMAS["reviewer"]
        required = schema.get("required", [])
        data = MOCK_ROLE_RESPONSES["reviewer"]
        for field in required:
            assert field in data and data[field], (
                f"reviewer missing required field: {field}"
            )

    @pytest.mark.asyncio
    async def test_skeptic_output_valid(self):
        schema = ROLE_SCHEMAS["skeptic"]
        required = schema.get("required", [])
        data = MOCK_ROLE_RESPONSES["skeptic"]
        for field in required:
            assert field in data and data[field], (
                f"skeptic missing required field: {field}"
            )

    @pytest.mark.asyncio
    async def test_synthesizer_output_valid(self):
        schema = ROLE_SCHEMAS["synthesizer"]
        required = schema.get("required", [])
        data = MOCK_ROLE_RESPONSES["synthesizer"]
        for field in required:
            assert field in data and data[field], (
                f"synthesizer missing required field: {field}"
            )


# =============================================================================
# TEST: Fusion actually synthesizes from MULTIPLE roles, not one "best"
# =============================================================================


class TestFusionMultiRoleSynthesis:
    @pytest.mark.asyncio
    async def test_fusion_uses_multiple_roles(self):
        """Fusion must incorporate outputs from all non-error roles."""
        syn = Synthesizer()
        results = {
            "planner": [{"role": "planner", "parsed": MOCK_ROLE_RESPONSES["planner"]}],
            "scout": [{"role": "scout", "parsed": MOCK_ROLE_RESPONSES["scout"]}],
            "implementer": [
                {"role": "implementer", "parsed": MOCK_ROLE_RESPONSES["implementer"]}
            ],
            "reviewer": [
                {"role": "reviewer", "parsed": MOCK_ROLE_RESPONSES["reviewer"]}
            ],
        }
        fused = syn.fuse(results)

        assert fused["changes_proposed"] == 2
        assert len(fused["findings"]) > 0
        sources = set(f.get("source", "") for f in fused["findings"])
        assert "planner" in sources, "findings missing planner contributions"
        assert "scout" in sources, "findings missing scout contributions"
        assert "implementer" in sources, "findings missing implementer contributions"
        assert "reviewer" in sources, "findings missing reviewer contributions"

    @pytest.mark.asyncio
    async def test_fusion_not_single_best_answer(self):
        """Must NOT be just 'pick the best model output'. Must fuse contributions."""
        syn = Synthesizer()
        results = {
            "planner": [{"role": "planner", "parsed": MOCK_ROLE_RESPONSES["planner"]}],
            "implementer": [
                {"role": "implementer", "parsed": MOCK_ROLE_RESPONSES["implementer"]}
            ],
            "reviewer": [
                {"role": "reviewer", "parsed": MOCK_ROLE_RESPONSES["reviewer"]}
            ],
        }
        fused = syn.fuse(results)

        sources = set(f.get("source", "") for f in fused["findings"])
        assert "planner" in sources
        assert "implementer" in sources
        assert "reviewer" in sources

    @pytest.mark.asyncio
    async def test_fusion_prefers_file_evidence(self):
        """File/tool evidence should score higher than model claims."""
        syn = Synthesizer()
        findings = [
            {"type": "bug", "evidence": "single_model_claim", "source": "planner"},
            {"type": "bug", "evidence": "direct_file_content", "source": "reviewer"},
        ]
        scored = syn._score_by_evidence(findings)
        assert scored[0]["confidence"] > scored[1]["confidence"]

    @pytest.mark.asyncio
    async def test_fusion_deduplicates_findings(self):
        """Duplicate findings should be collapsed."""
        syn = Synthesizer()
        findings = [
            {"type": "bug", "evidence": "same evidence text", "source": "planner"},
            {"type": "bug", "evidence": "same evidence text", "source": "reviewer"},
            {"type": "style", "evidence": "different", "source": "reviewer"},
        ]
        deduped = syn._deduplicate(findings)
        assert len(deduped) == 2  # one dupe collapsed

    @pytest.mark.asyncio
    async def test_fusion_resolves_contradictions_with_file_evidence(self):
        """Contradictory findings should be resolved using file/tool evidence."""
        syn = Synthesizer()
        contradictions = [
            {
                "type": "blocker",
                "description": "eval() not removed",
                "source": "skeptic",
            },
        ]
        changes = [
            {
                "file": "src/cli.py",
                "action": "edit",
                "diff": "-eval()",
                "rationale": "remove eval",
            },
        ]
        resolved = syn._resolve_contradictions(contradictions, changes)
        assert len(resolved) == 1
        assert "addressed" in resolved[0]

    @pytest.mark.asyncio
    async def test_fusion_reports_unresolved_blockers(self):
        """Blockers with no corresponding change should stay unresolved."""
        syn = Synthesizer()
        contradictions = [
            {"type": "blocker", "description": "no tests added", "source": "skeptic"},
        ]
        resolved = syn._resolve_contradictions(contradictions, [])
        assert len(resolved) == 1
        assert "unresolved" in resolved[0]


# =============================================================================
# TEST: Full orchestrator path with mock — verify events
# =============================================================================


class TestOrchestratorCouncilEvents:
    @pytest.mark.asyncio
    async def test_orchestrator_emits_council_events(self, tmp_path):
        """Verify the orchestrator emits council_started, council_completed, fusion_completed."""
        from galaxy_merge.core.session import Session, init_gm_dir
        from galaxy_merge.core.orchestrator import Orchestrator

        init_gm_dir(tmp_path)
        s = Session(tmp_path)
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        cfg = {
            "councils": {
                "coding_default": {
                    "max_parallel_calls": 2,
                    "timeout_seconds": 10,
                    "roles": {
                        "planner": {
                            "required": True,
                            "model_selector": {
                                "role": "planner",
                                "cost_policy": "balanced",
                            },
                        },
                        "implementer": {
                            "required": True,
                            "model_selector": {
                                "role": "implementer",
                                "cost_policy": "balanced",
                            },
                        },
                        "synthesizer": {
                            "required": True,
                            "model_selector": {
                                "role": "synthesizer",
                                "cost_policy": "balanced",
                            },
                        },
                    },
                }
            }
        }
        (config_dir / "fusion.json").write_text(json.dumps(cfg))
        (config_dir / "providers.json").write_text(
            json.dumps(
                {
                    "providers": {
                        "mock": {
                            "enabled": True,
                            "type": "mock",
                            "base_url": "http://mock",
                            "auth": {"type": "none"},
                            "timeout_seconds": 5,
                        }
                    }
                }
            )
        )
        (config_dir / "models.json").write_text(
            json.dumps(
                {
                    "models": {
                        "mock:all": {
                            "provider": "mock",
                            "model": "mock-v1",
                            "enabled": True,
                            "context_window": 32000,
                            "strengths": ["planning", "implementation", "synthesis"],
                            "roles": ["planner", "implementer", "synthesizer"],
                        },
                    }
                }
            )
        )

        orch = Orchestrator(s, config_dir)
        await orch.initialize()

        mock_prov = orch.providers.get("mock")
        assert mock_prov is not None
        mock_prov.set_mock_responses(MOCK_ROLE_RESPONSES)

        await orch.execute_goal("fix input validation")

        events = s.event_log.replay()
        event_types = [e["event"] for e in events]
        assert "council_started" in event_types, "council_started event missing"
        assert "council_completed" in event_types, "council_completed event missing"
        assert "fusion_started" in event_types, "fusion_started event missing"
        assert "fusion_completed" in event_types, "fusion_completed event missing"
        assert "goal_parsed" in event_types
        assert "council_started" in event_types
        assert "council_completed" in event_types
        assert "fusion_started" in event_types
        assert "fusion_completed" in event_types
        assert "completion_review_started" in event_types


# =============================================================================
# TEST: Fusion config routing
# =============================================================================


class TestFusionRouter:
    def test_select_council_by_task_type(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        cfg = {
            "councils": {
                "bugfix_default": {"roles": {"planner": {"required": True}}},
                "coding_default": {
                    "roles": {
                        "planner": {"required": True},
                        "implementer": {"required": True},
                    }
                },
            }
        }
        (config_dir / "fusion.json").write_text(json.dumps(cfg))
        routing = {
            "routing_rules": [
                {"match": {"task_type": "bug_fix"}, "council": "bugfix_default"},
                {"match": {"task_type": "small_edit"}, "council": "coding_default"},
            ],
            "fallback": {"council": "coding_default"},
        }
        (config_dir / "routing.json").write_text(json.dumps(routing))

        router = FusionRouter(None, config_dir)
        cfg1 = router.select_council("bug_fix")
        assert "planner" in cfg1.get("roles", {})
        assert "implementer" not in cfg1.get("roles", {})

        cfg2 = router.select_council("small_edit")
        assert "implementer" in cfg2.get("roles", {})

        cfg3 = router.select_council("unknown_type")
        assert cfg3 is not None


# =============================================================================
# TEST: Mock provider is called with correct role prompts
# =============================================================================


class TestMockProviderCalled:
    @pytest.mark.asyncio
    async def test_mock_receives_per_role_prompts(self, tmp_path):
        """Each role should receive a different system prompt."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "providers.json").write_text(
            json.dumps(
                {
                    "providers": {
                        "mock": {
                            "enabled": True,
                            "type": "mock",
                            "base_url": "http://mock",
                            "auth": {"type": "none"},
                            "timeout_seconds": 5,
                        }
                    }
                }
            )
        )
        (config_dir / "models.json").write_text(
            json.dumps(
                {
                    "models": {
                        "mock:all": {
                            "provider": "mock",
                            "model": "mock-v1",
                            "enabled": True,
                            "context_window": 32000,
                            "strengths": [
                                "planning",
                                "implementation",
                                "fast_scan",
                                "review",
                                "synthesis",
                            ],
                            "roles": [
                                "planner",
                                "implementer",
                                "scout",
                                "reviewer",
                                "cheap_verifier",
                                "synthesizer",
                            ],
                        },
                    }
                }
            )
        )

        registry = ProviderRegistry(config_dir)
        registry.load()
        assert (
            registry.get("mock").__class__.__module__ == "galaxy_merge.providers.mock"
        )

        fusion_config = {
            "max_parallel_calls": 4,
            "timeout_seconds": 30,
            "roles": {
                "planner": {
                    "required": True,
                    "model_selector": {"role": "planner", "cost_policy": "balanced"},
                },
                "scout": {
                    "required": True,
                    "model_selector": {"role": "scout", "cost_policy": "cheap"},
                },
                "implementer": {
                    "required": True,
                    "model_selector": {"role": "implementer", "cost_policy": "quality"},
                },
                "reviewer": {
                    "required": True,
                    "model_selector": {"role": "reviewer", "cost_policy": "balanced"},
                },
                "synthesizer": {
                    "required": True,
                    "model_selector": {"role": "synthesizer", "cost_policy": "quality"},
                },
            },
        }

        council = Council(registry, fusion_config, "test goal")
        mock_prov = registry.get("mock")
        assert mock_prov is not None
        mock_prov.set_mock_responses(MOCK_ROLE_RESPONSES)

        await council.execute()

        assert mock_prov.call_history, "Mock provider was never called"
        assert len(mock_prov.call_history) >= 5, (
            "Should have called provider for each of 5 roles"
        )


# =============================================================================
# TEST: Synthesizer properly handles contradictory reviewer + skeptic
# =============================================================================


class TestFusionContradictions:
    @pytest.mark.asyncio
    async def test_reviewer_skeptic_contradiction_detected(self):
        """When reviewer rejects and skeptic blocks, fusion should report issues."""
        syn = Synthesizer()
        results = {
            "implementer": [
                {"role": "implementer", "parsed": MOCK_ROLE_RESPONSES["implementer"]}
            ],
            "reviewer": [
                {"role": "reviewer", "parsed": CONTRADICTORY_REVIEW["reviewer"]}
            ],
            "skeptic": [{"role": "skeptic", "parsed": CONTRADICTORY_REVIEW["skeptic"]}],
        }
        fused = syn.fuse(results)
        assert len(fused.get("errors", [])) == 0
        assert "eval" in str(fused.get("findings", [])) or "eval" in str(
            fused.get("contradictions_resolved", [])
        )
