"""Shared valkey coordination: gpu_lock (fail-open) + concurrency semaphore.
Mirrors the glimmer supervisor and nova-mcp semaphore semantics."""

from __future__ import annotations

import os
import time
import uuid

VALKEY_HOST = os.environ.get("NOT_NOVA_ACT_VALKEY_HOST", "127.0.0.1")
VALKEY_PORT = int(os.environ.get("NOT_NOVA_ACT_VALKEY_PORT", "16379"))
GPU_LOCK_KEY = "gpu_lock"
SEMAPHORE_KEY = "not-nova-act:semaphore"
MAX_CONCURRENT = 3

_RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
  return redis.call("del", KEYS[1])
else
  return 0
end
"""


def get_valkey():
    import redis

    return redis.Redis(host=VALKEY_HOST, port=VALKEY_PORT, socket_timeout=5)


def acquire_gpu_lock(client, ttl_seconds: int = 600) -> str | None:
    """SET NX EX. Returns owner token, or None for fail-open when valkey
    is down (caller logs a warning and proceeds, like glimmer_supervisor)."""
    token = f"not-nova-act-{uuid.uuid4().hex[:8]}"
    try:
        if client.set(GPU_LOCK_KEY, token, nx=True, ex=ttl_seconds):
            return token
        return None  # held by someone else: caller should back off, not proceed
    except Exception:
        return None


def release_gpu_lock(client, token: str | None) -> bool:
    if not token:
        return False
    try:
        return bool(client.eval(_RELEASE_LUA, 1, GPU_LOCK_KEY, token))
    except Exception:
        return False


class Semaphore:
    """INCR/DECR counter with TTL refresh. Full → rate_limited, never raise."""

    def __init__(self, client, key: str = SEMAPHORE_KEY,
                 max_concurrent: int = MAX_CONCURRENT, ttl_seconds: int = 120):
        self.client = client
        self.key = key
        self.max_concurrent = max_concurrent
        self.ttl_seconds = ttl_seconds
        self.held = False

    def acquire(self) -> bool:
        try:
            count = self.client.incr(self.key)
            if count == 1 or count > self.max_concurrent:
                self.client.expire(self.key, self.ttl_seconds)
            if count > self.max_concurrent:
                self.client.decr(self.key)
                return False
            self.held = True
            return True
        except Exception:
            return False  # fail-open like the supervisor

    def release(self) -> None:
        if not self.held:
            return
        try:
            count = self.client.decr(self.key)
            if count < 0:
                self.client.set(self.key, 0)
        except Exception:
            pass
        finally:
            self.held = False

    def __enter__(self) -> "Semaphore":
        return self

    def __exit__(self, *exc) -> None:
        self.release()
