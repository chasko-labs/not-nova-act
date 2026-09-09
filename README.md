# not-nova-act

Local-first rebuild of everything Amazon Nova Act does: browser action (`act`),
structured extraction (`act_get`), multi-step workflows, screenshots, DOM checks,
model registry — on Playwright plus small local vision models. No AWS, no API
keys, no hosted model calls by default.

- planner/vision: `qwen3-vl:8b` via ollama (`localhost:11434`)
- reasoner fallback: `glimmer-30b` via supervisor (`:8181`)
- grounding assist: cached CLIP + dinov2 weights (re-rank only, never plan)
- hands: Playwright sync API only
- patterns reused: `fc-pool` microVM shape, valkey `gpu_lock` + semaphore,
  dockerized MCP layout from `heraldstack-mcp`

Start at [ARCHITECTURE.md](./ARCHITECTURE.md): capability matrix, perceive
pipeline, reason+act loop, hosting shape, 7-tool MCP map, eval battery, and the
dependency-ordered work breakdown.
