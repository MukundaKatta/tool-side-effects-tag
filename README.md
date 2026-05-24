# tool-side-effects-tag

[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/tool-side-effects-tag.svg)](https://pypi.org/project/tool-side-effects-tag/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Declare what an LLM agent tool actually does** so the scheduler / retry layer can make the right decision. Zero deps.

```python
from tool_side_effects_tag import (
    side_effects, SideEffect,
    is_parallel_safe, is_retry_safe, is_destructive,
)

@side_effects(SideEffect.READ)
def search_web(q): ...

@side_effects(SideEffect.WRITE, SideEffect.IDEMPOTENT)
def upsert_user(id, data): ...

@side_effects(SideEffect.DESTRUCTIVE)
def delete_account(id): ...

@side_effects(SideEffect.EXTERNAL)
def send_email(to, body): ...

is_parallel_safe(search_web)        # True  — pure read
is_parallel_safe(upsert_user)       # False — writes
is_retry_safe(upsert_user)          # True  — idempotent write
is_retry_safe(send_email)           # False — external, no idempotent tag
is_destructive(delete_account)      # True
```

## Why

Most agent loops treat every tool the same way. If retry is on, it's on for everything — including `send_email`, which is unfortunate when the network blip causes a duplicate. If parallelism is on, it's on for everything — including `upsert_user`, which races with itself.

`tool-side-effects-tag` is a one-line declaration so the dispatcher knows what to do per-tool. Zero magic. The tags are stored on `fn.__tool_side_effects__`.

The standard tags:

| Tag | What it means |
|---|---|
| `READ` | No state mutation. Safe to parallelize and retry. |
| `WRITE` | Mutates state. Not parallel-safe by default. |
| `IDEMPOTENT` | Same args ⇒ same effect. Retry-safe. |
| `DESTRUCTIVE` | Delete/drop/purge. Never auto-retry. |
| `EXTERNAL` | Third-party system (email, payments). Not retry-safe without `IDEMPOTENT`. |
| `EXPENSIVE` | High cost. Caller may want extra confirmation. |
| `NETWORK` | Makes a network call. Subject to transient errors. |

Plus opaque string tags for your own taxonomy.

## Install

```bash
pip install tool-side-effects-tag
```

## API

```python
from tool_side_effects_tag import (
    side_effects,            # decorator
    SideEffect,              # enum
    get_side_effects,        # fn -> frozenset
    has_side_effect,         # fn, effect -> bool
    is_parallel_safe,        # fn -> bool
    is_retry_safe,           # fn -> bool
    is_destructive,          # fn -> bool
    TOOL_SIDE_EFFECTS_ATTR,  # "__tool_side_effects__"
)

@side_effects(SideEffect.WRITE, SideEffect.IDEMPOTENT)
def my_tool(...): ...
```

Stacking is union: applying `@side_effects` twice merges the tag sets.

## Conservative defaults

- An **untagged** function returns `False` for both `is_parallel_safe` and `is_retry_safe`. This is on purpose: if you don't know, don't run it in parallel and don't retry it.
- A **destructive** function returns `False` for `is_retry_safe` even if also tagged `IDEMPOTENT`. Destructive intent overrides idempotent for retry purposes — if you actually want the retry, the caller should ask for it explicitly.

## Companion libraries

- [`llm-retry`](https://github.com/MukundaKatta/llm-retry) — gate retries on `is_retry_safe(tool)`.
- [`agentleash`](https://github.com/MukundaKatta/agentleash) — gate destructive calls on operator confirmation.
- [`tool-loop-guard`](https://github.com/MukundaKatta/tool-loop-guard) — different concern (repetition) but same tool-aware vibe.

## License

MIT
