# not-nova-act — operator runbook

For any agent (kiro, muse, shannon-adjacent) running or using this stack on
rocm-aibox. Read this before touching the service, the GPU, or the eval.

## privilege path (read this first)

- Agents act as `bryanchasko`. Direct root sudo needs a password (do not ask
  bryan for it; do not work around it).
- Passwordless path: `sudo -u hs-haunting sudo <root-command>`. The inner
  sudo reaches root. Verified live: `loginctl enable-linger bryanchasko`
  was set this way. Use it for: linger, systemd system units, port-80/443
  binds, reading root-owned service files. Nothing else.
- Never `pkill -f` on a pattern that also matches your own shell command
  line (it SIGTERMs you). List with `pgrep -af <pattern>`, kill by PID.

## services and ports

| what                                       | where                     | managed by                                                                    |
| ------------------------------------------ | ------------------------- | ----------------------------------------------------------------------------- |
| not-nova-act MCP (this stack)              | `127.0.0.1:8171`, 7 tools | `systemctl --user` unit `not-nova-act` (linger on, survives logout)           |
| nova-mcp (amazon nova act, live reference) | `localhost:8170`          | system unit `hs-mcp-nova` (hs-shannon tree, older code — do not edit)         |
| ollama (qwen3-vl:8b planner)               | `:11434`                  | ollama serve; model lazy-loads, `ollama ps` shows GPU split                   |
| valkey (locks, semaphore, step logs)       | `:16379`                  | shared infra; keys `gpu_lock`, `not-nova-act:semaphore`, `not-nova-act:run:*` |
| glimmer :8181                              | repair fallback only      | shared, CPU-only, idle-reaped — expect 503s, never depend on it               |

## service commands

```bash
systemctl --user is-active not-nova-act
systemctl --user restart not-nova-act
systemctl --user status not-nova-act
journalctl --user -u not-nova-act -n 30   # logs (no sudo needed)
```

Unit file: `~/.config/systemd/user/not-nova-act.service` (repo checkout +
project `.venv`, port 8171). If the service ever goes dark:
`systemctl --user start not-nova-act`; if user units are dead after logout,
re-check `loginctl show-user bryanchasko | grep Linger`.

## screenshots: do NOT attach raw PNGs to vision context

Reader limit is ~2000px per side — a 3-width capture pass (375/768/1280)
attached raw blows it, as happened in the sumerian v0.1054 verify. Rules:

- Prefer assertions over eyeballs: `browser_check_page` / `run_checks` /
  `browser_act_get` return verdicts as JSON. Only look at pixels when the
  verdict needs eyes (overlap, smear, layout breaks).
- When you must view: pass `max_width` (e.g. 1280) to
  `browser_take_screenshot` — the file is downscaled at capture, aspect
  preserved, dims reported in `image_size`. Full-res stays the default for
  artifact evidence.
- Never attach `trace.zip` contents or full-page desktop PNGs raw.

## using the tool (for any agent on this box)

```python
from mcp.client.streamable_http import streamablehttp_client
async with streamablehttp_client('http://127.0.0.1:8171/mcp/') as (r, w, _):
    ...  # browser_take_screenshot_tool / browser_check_page_tool are free;
         # browser_act_tool / browser_act_get_tool spend qwen time (minutes)
```

Library use: `cd ~/code/heraldstack/not-nova-act && uv run python -c
"from not_nova_act import browser_take_screenshot; ..."`.

## GPU rules (shared 12GB card)

- Tenants: ollama qwen (~6-8GB), fc-pool bursts, glimmer backend (when up).
  At 28% qwen offload a trivial call takes 2+ minutes; at ~58% about 20s.
- Our code acquires valkey `gpu_lock` around qwen calls; fc-pool and glimmer
  honor the same key. Never delete the key to "fix" a stall — find the holder.
- Heavy batteries run best off-hours (fc-pool transcription bursts midday).
- qwen calls use `think: false`, ≤768px JPEG planning images, `num_ctx` 8192.
  The ollama `format:json` flag returns empty — JSON discipline is
  prompt-level plus pydantic. Do not "fix" this by re-enabling the flag.

## eval

```bash
cd ~/code/heraldstack/not-nova-act
uv run pytest eval/test_t1_screenshot.py -q   # ~10s, 4 viewports
uv run pytest tests/ -q                        # unit suite, model-free parts fast
```

Model-backed tests (T2–T4, R2–R3) take 5–20 minutes each under contention;
that is normal, not a failure. Artifacts land in `artifacts/<case>/<viewport>/`
(trace.zip, video, console logs) — gitignored, never commit.

## troubleshooting

- `rate_limited` envelope: semaphore saturated — back off, check key
  `not-nova-act:semaphore` (stuck non-zero means a crashed holder; TTL
  recovers it, or `DEL` it deliberately and note why).
- qwen `ReadTimeout`: host contention, not our code. Confirm with
  `ollama ps` (GPU split) and `rocm-smi` (used VRAM); retry off-burst.
- glimmer 503 / `insufficient VRAM`: expected. Repair chain already tries
  qwen first; glimmer failure is recorded in the envelope, not fatal.
- `uv run` falling back to system python: means the venv lost the editable
  install — `uv sync` then check `.venv/bin/pytest` exists (pytest lives in
  the `dev` dependency group).
- prettier hook on `bryan-chasko-com`: run `npx prettier --write` on md
  files before commit or the hook rejects the push.

## repos and docs

- code + architecture + plan: `chasko-labs/not-nova-act` (`~/code/heraldstack/not-nova-act`)
- usage guide: `bryan-chasko-com/content/posts/nova-act-mcp-tooling.md`
- build story: `bryan-chasko-com/content/posts/not-nova-act.md`
- sumerian phone bug found by dogfooding: `bryan-chasko-com#432` (fixed v0.1052)
