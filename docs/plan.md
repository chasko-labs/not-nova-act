# not-nova-act — build plan

## Goal

Working local-first replacement for Nova Act's browser-use surface: `act`,
`act_get`, workflows, screenshots, DOM checks, model registry, MCP server —
running on Playwright + qwen3-vl:8b, provable against the eval battery.

## Success Criteria

- `browser_act` fills and submits a real form from one NL command; `browser_act_get` extracts a product list to schema-valid JSON.
- T1–T4 eval battery passes on all four viewports with trace/video/screenshot artifacts per case.
- MCP server exposes all 7 tools with `{completed|rate_limited|timeout|error}` envelopes; `tools/list` shows the 7 names.
- Zero AWS calls in the default path (assert by running the battery with no AWS credentials in env).

## Context And Current Facts

- Seed architecture: `ARCHITECTURE.md` (§2 matrix, §3 perceive order, §4 loop, §6 tool map, §7 battery, §8 breakdown) in `chasko-labs/not-nova-act`, `main` at `12d24e4`.
- Verified live this session: `qwen3-vl:8b` (8.8B Q4_K_M, 58% GPU, 28k context) read a 480px example.com screenshot and returned `'The webpage displays the title "Example Domain" with explanatory text ... accompanied by a "Learn more" link.'` Caution: `format:json` on `/api/generate` returned empty; plain prompt worked — JSON discipline needs prompt-level enforcement, not API-level.
- Services UP: ollama `:11434`, valkey `:16379`, glimmer `:8181`.
- Reuse sources: `heraldstack-mcp/servers/nova-mcp/microvm/browser_tools.py` (envelopes, semaphore, `max_steps=5` observation heuristic), `server.py` (FastMCP shape), `servers/nova-mcp/microvm/Dockerfile` (system chromium deps) and the simpler `servers/s3vectors-mcp/Dockerfile`, `glimmer_supervisor.py` (gpu_lock fail-open, idle reaper), fc-pool `gpu_lock` on valkey.
- Toolchain: `uv` present, python 3.12, Playwright chromium browsers installed, global prettier hook (run `npx prettier --write` on md before commit).

## Constraints And Non-goals

- No hosted model calls by default; IAM/RolesAnywhere path stays deleted (opt-in fallback is out of scope for the build).
- No new abstraction beyond ARCHITECTURE.md: thin Playwright wrappers, pure-Python Workflow, FastMCP server mirroring nova-mcp layout.
- CLIP/dinov2 re-rank is step 5 hardening only — never on the critical path of units 1–4.
- No frontend, no hosted deploy, no auth system in this plan.

## Key Decisions

- Perceive order fixed: a11y tree → boxes → screenshot → (re-rank) → qwen → glimmer fallback. Rejected SoM-first: deterministic signals are cheaper and cover ~70% of groundings; SoM stays an unlabeled future experiment.
- Model-free units first (units 1–2 need zero GPU). Rejected model-first: leaves nothing testable if qwen grounding stalls.
- `uv` + project `.venv` for the Python env (house rule: env lives with the project, never system interpreter).
- Trunk commits, one per work unit, pushed to `main` (solo dev, new repo). Rejected PR-per-unit: review overhead with no reviewer; revisit when a second contributor joins.
- Qwen JSON via constrained prompting + pydantic validation + glimmer repair, not `/api` format flags (verified empty-response failure above).

## Recommended Approach

Follow ARCHITECTURE.md §8 order exactly: hands → observe → act loop → act_get → re-rank → Workflow → eval battery → MCP dockerization. Each unit lands with its validation evidence before the next starts.

## Work Plan

1. **Hands + 4 free tools** (`browser_session`, `browser_take_screenshot`, `browser_check_page`, `browser_list_models`). Thin sync wrappers returning `StepResult`; registry reads `ollama list` + HF cache scan. No model.
2. **Observe + logging** (screenshot + a11y snapshot + ≤30 boxes; valkey step-log stream; tracing + video artifacts to `artifacts/<case>/<viewport>/`).
3. **`browser_act` loop** (qwen plan JSON → dispatch → screenshot-diff verify; `gpu_lock` acquire/release; semaphore `INCR/DECR`, max 3, TTL 2×timeout).
4. **`browser_act_get`** (terminal-step constrained decode, pydantic validate, glimmer repair on fail, retry cap).
5. **CLIP/dinov2 re-rank assist** (crop scoring vs referring expression; used only on low confidence / duplicate names).
6. **`Workflow` runner + `browser_workflow`** (YAML/JSON defs, shared context, `starting_page` fixture, `on_error` policy).
7. **Eval battery T1–T4** (viewport matrix 480/768/1280/1920, golden files + `toHaveScreenshot` desktop baseline).
8. **MCP server + dockerization** (FastMCP streamable-http mirroring nova-mcp layout, parity envelopes, `Dockerfile` after s3vectors pattern, docs).

## Validation Plan

- Unit 1: `browser_take_screenshot("https://example.com")` returns existing PNG; `browser_check_page` asserts heading; `browser_list_models` names `qwen3-vl:8b`.
- Unit 2: observe output contains screenshot bytes + a11y names + boxes; valkey stream has the step entry.
- Unit 3: one NL form-fill + submit succeeds; `screenshot_before/after` differ; semaphore count returns to baseline.
- Unit 4: product-list extraction validates against pydantic schema and matches golden file.
- Unit 5: duplicate-name fixture resolves to the correct box where qwen-only picked wrong (record the fixture).
- Unit 6: 3-step YAML def (goto → act → act_get) shares context across steps.
- Unit 7: full battery green on all 4 viewports; highest-risk step — qwen grounding accuracy on real pages, measured per-case not vibes.
- Unit 8: `tools/list` shows all 7 names; unknown-tool and `rate_limited` paths return envelopes, never raise; battery passes with AWS env stripped.

## Risks / Rollback

- Qwen grounding too weak for small/ambiguous targets: mitigated by perceive order + unit 5 + glimmer fallback; rollback is narrowing supported action set, not architecture change.
- GPU contention with fc-pool/glimmer: `gpu_lock` serializes; fail-open only logs.
- Ollama `format:json` unreliability (observed): prompt-level JSON + pydantic + repair path instead.
- Rollback per unit: revert the unit commit; units are additive so revert is clean.

## Open Questions

None. All material choices (repo, model, order, scope) are decided above.

## Sources

No external sources informed this plan; all evidence is workspace-local (live probes and repo reads this session).
