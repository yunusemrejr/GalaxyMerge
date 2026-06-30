# Council and Fusion System

## Overview

The council system processes goals through multiple LLM roles in parallel, then fuses the results by evidence ranking.

## Council Roles

| Role | Purpose | Required |
|------|---------|----------|
| `planner` | Create minimal safe execution plan | Yes |
| `scout` | Inspect workspace evidence quickly | No |
| `implementer` | Produce patch candidates | Yes |
| `reviewer` | Find bugs and risks in proposed changes | Yes |
| `skeptic` | Argue why the goal may not be complete | No |
| `cheap_verifier` | Quick syntax and basic correctness check | No |
| `synthesizer` | Fuse council outputs into one coherent action | Yes |

## Execution Flow

1. `FusionRouter.select_council(task_type)` selects council config from `fusion.json` based on `routing.json` rules
2. `Council.execute()` spawns parallel async tasks for each required role
3. Each role:
   - Selects best model via `ProviderRegistry.select_best_model(role, cost_policy)`
   - Builds prompt via `PromptAssembly` (stable prefix + dynamic goal)
   - Calls `provider.chat_completion(messages, model)`
   - Parses JSON response, validates against role schema
   - On failure: retries with backoff, falls back to next provider
4. Results collected with semaphore-based concurrency limit
5. Minimum quorum check (if configured)

## Model Selection

`ProviderRegistry.select_best_model(role, cost_policy, prefer_strengths)`:
- Filters models by role assignment
- Filters by minimum context window per role
- Scores by: strength match, cost tier, latency tier, prefix cache support, context window size
- Returns highest-scoring available model

## Retry & Fallback

- Per-provider retry with exponential backoff (configurable `retry_backoff`, `retry_backoff_max`)
- On provider exhaustion: `_find_fallback()` selects next healthy provider for the role
- Failed providers marked unhealthy to prevent cycling
- Provider errors classified: `auth`, `rate_limit`, `timeout`, `server_error`, `context_limit`, `invalid_response`, `stream_disconnect`

## Synthesis

`Synthesizer.fuse(council_results)`:
1. Collects findings from all roles
2. Deduplicates by evidence content
3. Scores by evidence ranking (direct_file_content > test_output > ... > unsupported_assumption)
4. Resolves contradictions (skeptic blockers vs implementer changes)
5. Tracks missing perspectives (roles that failed)
6. Computes completion confidence (1.0 - penalties for missing roles/errors)
7. Builds execution plan from implementer changes

## Prompt Assembly

`PromptAssembly` (in `token/segments.py`) builds cache-friendly prompts:
- **Stable segments**: role definition, output schema (cache-reusable)
- **Dynamic segments**: goal text (changes per task)
- Segments sorted: stable → semi_stable → dynamic → volatile
- Hash-based cache tracking for provider-side prefix caching

## Post-Fusion Review

`review_fusion_result(fused)` checks:
- Plan is non-empty
- No unresolved blockers
- Completion confidence above threshold
