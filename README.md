# not-nova-act

Local-first rebuild of everything Amazon Nova Act does: browser action (`act`),
structured extraction (`act_get`), multi-step workflows, screenshots, DOM checks,
model registry — on Playwright plus small local vision models. No AWS, no API
keys, no hosted model calls by default.

- Sees screenshots and plans the next click with a local vision model
  (`qwen3-vl:8b`) served by ollama — nothing leaves the machine.
- When the plan is uncertain, a larger local model (`glimmer-30b`)
  double-checks it before acting.
- Small cached vision models rank which on-screen element matches a
  description; they never decide actions.
- Clicks and types through Playwright, the standard browser-automation library.
- One browser action runs at a time (a shared lock guards the GPU), and
  agents talk to it over the standard model-context protocol (MCP).

Start at [ARCHITECTURE.md](./ARCHITECTURE.md): capability matrix, perceive
pipeline, reason+act loop, hosting shape, 7-tool MCP map, eval battery, and the
dependency-ordered work breakdown.

Testing a Chrome extension with agents: [docs/extension-testing.md](./docs/extension-testing.md) —
deterministic `check_page` assertions on `chrome-extension://` pages via the
per-call `extension_path` parameter, with model calls reserved for what
determinism can't reach.
