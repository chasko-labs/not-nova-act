# not-nova-act — ARCHITECTURE.md (seed)

## 1. Goal

Local-first rebuild of Nova Act browser-use API. No AWS, no API keys, no hosted model calls by default.

- Planner/vision: `qwen3-vl:8b` via Ollama `localhost:11434` (chat/completions, vision JSON mode).
- Reasoner fallback: `glimmer-30b` via supervisor `:8181` (OpenAI-compat) for multi-step plans, disambiguation, `act_get` repair.
- Grounding assist (cached, no download): CLIP `vit-base`/`large` + `dinov2-small` from HF cache for element relevance re-rank only.
- Hands: Playwright sync API only.
- Host patterns reused: `fc-pool` Firecracker microVM shape, `valkey gpu_lock:16379` GPU serialization, dockerized MCP server layout under `heraldstack-mcp/servers`, tool surface from `servers/nova-mcp/microvm/browser_tools.py`.

Repo: `chasko-labs/not-nova-act`. Concrete deliverable, no filler.

## 2. Capability matrix (Nova Act feature → local rebuild → status)

| Nova Act feature                                             | Local rebuild                                                                                                                                                                                                                                     | Status                  |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- |
| `act(prompt, browser)`                                       | `act()`: screenshot → qwen3-vl-8b JSON `{action: click\|type\|scroll\|select\|wait\|done, target_ref, text, confidence}` → CLIP/dinov2 re-rank of candidate boxes from Playwright a11y tree + bounding boxes → Playwright locator dispatch → loop | implement first         |
| `act_get(schema, prompt)`                                    | same observe loop, terminal step constrained-decode to JSON; validate with pydantic; glimmer-30b coerces/repairs on parse fail; retry cap                                                                                                         | implement first         |
| `Workflow` (multi-act DAG, inputs dict, `act()` composition) | pure-Python `Workflow` class: `steps=[callables]`, shared dict context, `starting_page` fixture, per-step `max_steps` cap, `on_error: fail\|continue`, sequential runner                                                                          | implement first         |
| steps + `max_steps`/timeout                                  | step loop: `observe→plan→execute→verify` (screenshot diff / expected-text check); `timeout_seconds` per act; parity defaults `max_steps 10–25`                                                                                                    | implement first         |
| tools (click/type/scroll/navigate/back/hover/select/upload)  | thin wrappers over Playwright sync `Page` methods; each returns `StepResult(ok, observation, artifacts)`; same signatures as `browser_tools.py` so WORK half is drop-in                                                                           | implement first         |
| `ListModels`/aliases                                         | local registry endpoint: `ollama list` (qwen3-vl:8b, glimmer:30b) + HF cache scan (CLIP, dinov2); alias map                                                                                                                                       | implement second        |
| session history                                              | valkey streams for step log + screenshot refs; qdrant optional semantic recall                                                                                                                                                                    | implement second        |
| `invoke_nova_act_workflow` (hosted SDK)                      | deleted; replaced by local `Workflow` runner; IAM path kept only as opt-in cloud fallback, off by default                                                                                                                                         | drop                    |
| api-key vs IAM auth                                          | deleted; local = no auth (Ollama + Playwright on localhost)                                                                                                                                                                                       | drop                    |
| screenshots                                                  | `page.screenshot` (`full_page=False` in act loop, 1280px viewport; `full_page` flag kept for parity); semantics mirror `nova_take_screenshot(wait_seconds, full_page)`                                                                            | reuse Playwright native |
| logs / video / tracing                                       | `context.tracing` (screenshots+snapshots) + `recordVideo`; console/pageerror/requestfailed listeners; step logs to valkey + local `.log`; artifacts to `artifacts/<case>/<viewport>/`                                                             | reuse Playwright native |
| checks (`nova_check_page` DOM assertions)                    | Playwright locator asserts, no model: `exists, text_eq, text_contains, count_eq, attr_eq, visible, a11y_role(name)`, web-first auto-wait locators                                                                                                 | reuse Playwright native |

MCP surface parity: the 7 nova-mcp tools map to 7 local tools (see §6); hosted envelopes `{completed|rate_limited|timeout|error}` kept, never raise.

## 3. Perceive pipeline

Order is load-bearing. Cheapest deterministic signal first, model last.

1. **A11y tree + DOM text** — Playwright accessibility snapshot + `page.content` excerpt. Cheapest, fastest, deterministic. Handles ~70% of groundings (forms, buttons with names, links).
2. **Bounding-box candidates** — `locator.bounding_box()` for visible candidates matching a11y role/name filter. Cap ~30 candidates/step.
3. **Screenshot** — 1280px viewport, `full_page=False` in loop (full page only for `take_screenshot` tool / eval evidence). PNG bytes → qwen.
4. **CLIP/dinov2 re-rank** — cached models score candidate crops vs referring expression; re-rank only, never plan. Used when qwen confidence low or multiple same-name matches.
5. **qwen3-vl-8b plan** — vision input (screenshot + annotated candidate list + DOM excerpt) → action JSON. JSON mode / constrained decode.
6. **glimmer-30b fallback** — triggered on: qwen confidence < threshold, JSON parse fail ×2, or multi-step plan needed. Coerces/repairs JSON to pydantic model.

No model call for DOM assertions — checks are pure locators.

## 4. Reason + act loop

```
while steps < max_steps and not done and within timeout_seconds:
    obs     = observe()        # screenshot + a11y snapshot + boxes
    plan    = qwen.plan(obs)   # {action, target_ref, text, confidence}
    if plan.confidence < T: plan = glimmer.repair_or_replan(obs, plan)
    ranked  = clip_rerank(plan.target_ref, candidates)  # assist only
    result  = hands.dispatch(ranked.top or plan.target_ref)  # StepResult
    verify  = check(result)    # screenshot diff / expected-text / locator assert
    log(step, obs_ref, plan, result, verify)  # valkey stream + .log
```

- `hands.dispatch`: `goto/click/fill/scroll/select/hover/back/screenshot/pdf` — thin Playwright wrappers.
- `verify`: per-step screenshot_before/after + DOM check; failure → retry same step (budget counts) or `on_error` policy.
- `act_get`: identical loop; terminal step decodes to schema-constrained JSON, pydantic-validated, glimmer repairs.
- `Workflow`: steps list of `act`/`act_get`/assert callables sharing `BrowserSession` + dict context; per-step screenshot+snapshot; `starting_page` fixture.
- GPU serialization: acquire `gpu_lock` (`SET NX EX` + owner-safe release) before any qwen/glimmer call; fail-open with warning if valkey down (mirrors `glimmer_supervisor.py`).
- Concurrency: valkey counter `nova-act:semaphore`, `INCR/DECR`, `MAX_CONCURRENT=3`, TTL=2×timeout, floor-at-0, try/finally.

## 5. Hosting shape

- **Runtime**: local process first; `fc-pool` microVM optional for isolation (stable public port + lazy cold-start backend pattern from `glimmer_supervisor.py`).
- **Models**: Ollama `:11434` (qwen3-vl:8b); supervisor `:8181` (glimmer-30b) with VRAM floor check, idle reaper (300s), single-flight mutex, double-detached backend (pidfile-tracked).
- **MCP server**: FastMCP streamable-http, dockerized under `heraldstack-mcp/servers` layout; pure-Playwright tools still take semaphore slots (parity with nova-mcp).
- **State**: valkey `127.0.0.1:16379`; streams for step logs, `gpu_lock` for GPU, `nova-act:semaphore` for concurrency.
- **Auth**: none locally. IAM path exists only as disabled fallback.

## 6. MCP tool map (7 tools)

| #   | Tool                      | Semantics                                                                                   | Model cost               |
| --- | ------------------------- | ------------------------------------------------------------------------------------------- | ------------------------ |
| 1   | `browser_session`         | open/navigate/close session; `starting_page`, viewport fixture                              | none                     |
| 2   | `browser_act`             | one NL action step (plan+dispatch+verify)                                                   | qwen (+glimmer fallback) |
| 3   | `browser_act_get`         | NL extract → schema-constrained JSON, pydantic-validated                                    | qwen (+glimmer repair)   |
| 4   | `browser_workflow`        | run `Workflow` def (YAML/JSON → stepper); sequential, `on_error` policy                     | per-step as above        |
| 5   | `browser_take_screenshot` | `wait_seconds`, `full_page`; save + return path                                             | none                     |
| 6   | `browser_check_page`      | DOM assertions (`exists/text_eq/text_contains/count_eq/attr_eq/visible/a11y_role/evaluate`) | none                     |
| 7   | `browser_list_models`     | local registry: ollama list + HF cache scan + alias map                                     | none                     |

Envelopes `{completed|rate_limited|timeout|error}`; never raise.

## 7. Eval battery (`eval/`, parity proof)

Harness (`conftest`): viewport matrix `480×800 phone / 768×1024 tablet / 1280×800 desktop / 1920×1080 wide`; chromium headless; `tracing.start({screenshots:true,snapshots:true})` + video on; per-case output `artifacts/<case>/<viewport>/` (trace.zip + video + screenshots + console/network capture).

- **T1 screenshot**: goto example page; full-page screenshot exists; no console errors.
- **T2 act**: NL click/typing task (e.g. fill form, submit); assert via `text_contains` + `visible`; screenshot_before/after diff shows change.
- **T3 act_get**: structured extract (e.g. product list → `[{name, price}]`); pydantic validation passes; golden-file compare.
- **T4 workflow**: 3-step def (goto → act → act_get) with shared context; all per-step screenshots+snapshots present; `expect(page).toHaveScreenshot(baseline)` visual parity on desktop viewport.

## 8. Work breakdown (dependency order)

1. Playwright hands + `StepResult` + `browser_session/check_page/take_screenshot/list_models` (no model). Unblocks everything testable.
2. Observe (screenshot+a11y+boxes) + valkey step log + tracing/video artifacts. Unblocks eval harness.
3. `act()` loop with qwen3-vl-8b + `gpu_lock` + semaphore. Proves T2.
4. `act_get()` constrained decode + pydantic + glimmer repair. Proves T3.
5. CLIP/dinov2 re-rank assist. Hardens grounding.
6. `Workflow` runner + `browser_workflow` + YAML/JSON def. Proves T4.
7. Eval battery T1–T4 + viewport matrix + baselines.
8. MCP server dockerization + parity envelopes + docs.
