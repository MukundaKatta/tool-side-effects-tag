"""tool-side-effects-tag - declare what an agent tool actually does.

If your scheduler doesn't know which tools are reads and which are
writes, it can't run them in parallel safely. If your retry layer
doesn't know which tools are idempotent, it can't retry them safely.

`@side_effects(...)` puts a tiny declaration on the function. Inspection
helpers let the scheduler / retry / dispatch layer make the right
decision per-tool.

    from tool_side_effects_tag import (
        side_effects, SideEffect, is_parallel_safe, is_retry_safe,
        get_side_effects,
    )

    @side_effects(SideEffect.READ)
    def search_web(q: str): ...

    @side_effects(SideEffect.WRITE, SideEffect.IDEMPOTENT)
    def upsert_user(id: str, data: dict): ...

    @side_effects(SideEffect.DESTRUCTIVE)
    def delete_account(id: str): ...

    @side_effects(SideEffect.EXTERNAL)
    def send_email(to: str, body: str): ...

    get_side_effects(search_web)          # frozenset{SideEffect.READ}
    is_parallel_safe(search_web)          # True  — read-only
    is_parallel_safe(upsert_user)         # False — writes
    is_retry_safe(upsert_user)            # True  — idempotent write
    is_retry_safe(send_email)             # False — external, no idempotent tag
"""

from __future__ import annotations

from enum import Enum
from functools import wraps
from typing import Any, Callable, FrozenSet, TypeVar

__version__ = "0.1.0"
__all__ = [
    "SideEffect",
    "side_effects",
    "get_side_effects",
    "is_parallel_safe",
    "is_retry_safe",
    "is_destructive",
    "has_side_effect",
    "TOOL_SIDE_EFFECTS_ATTR",
]


T = TypeVar("T", bound=Callable[..., Any])


class SideEffect(str, Enum):
    """Standard side-effect categories. Inherits from `str` for JSON-friendliness."""

    READ = "read"
    """Reads data. No state mutation. Safe to parallelize and retry."""

    WRITE = "write"
    """Mutates internal/state. Not parallel-safe by default."""

    IDEMPOTENT = "idempotent"
    """Repeated calls with same args produce the same effect. Retry-safe."""

    DESTRUCTIVE = "destructive"
    """Removes or invalidates state (delete, drop, purge). Never auto-retry."""

    EXTERNAL = "external"
    """Touches a third-party system (email, payments, webhooks). Not retry-safe without IDEMPOTENT."""

    EXPENSIVE = "expensive"
    """High cost (tokens, money, time). Caller may want extra confirmation."""

    NETWORK = "network"
    """Makes a network call. Subject to retryable transient errors."""


TOOL_SIDE_EFFECTS_ATTR = "__tool_side_effects__"


def side_effects(*effects: SideEffect | str) -> Callable[[T], T]:
    """Decorator: attach a frozenset of side-effect tags to a function.

    Effects can be `SideEffect` values or plain strings (treated as opaque
    custom tags). The full set is stored on the function as
    `__tool_side_effects__`.

    Stacks: applying the decorator twice unions the sets.
    """
    normalized: list[SideEffect | str] = []
    for e in effects:
        if isinstance(e, SideEffect):
            normalized.append(e)
        elif isinstance(e, str):
            # Allow plain strings; try to map to SideEffect if possible
            try:
                normalized.append(SideEffect(e))
            except ValueError:
                normalized.append(e)  # opaque custom tag
        else:
            raise TypeError(
                f"side_effects(...) takes SideEffect or str, got {type(e).__name__}"
            )

    def decorator(fn: T) -> T:
        existing = getattr(fn, TOOL_SIDE_EFFECTS_ATTR, frozenset())
        merged = frozenset(existing | frozenset(normalized))
        try:
            setattr(fn, TOOL_SIDE_EFFECTS_ATTR, merged)
            return fn
        except (AttributeError, TypeError):
            # builtins / slotted objects can't take new attrs; wrap.
            @wraps(fn)
            def wrapper(*args: Any, **kwargs: Any):
                return fn(*args, **kwargs)

            setattr(wrapper, TOOL_SIDE_EFFECTS_ATTR, merged)
            return wrapper  # type: ignore[return-value]

    return decorator


def get_side_effects(fn: Any) -> FrozenSet[SideEffect | str]:
    """Return the tags attached to `fn`, or an empty frozenset if untagged."""
    return getattr(fn, TOOL_SIDE_EFFECTS_ATTR, frozenset())


def has_side_effect(fn: Any, effect: SideEffect | str) -> bool:
    """True if `fn` has the given effect tag."""
    return effect in get_side_effects(fn)


def is_parallel_safe(fn: Any) -> bool:
    """Safe to run alongside other tools.

    Rules:
      - READ-only with no WRITE / DESTRUCTIVE → safe.
      - WRITE / DESTRUCTIVE present → not safe.
      - Untagged → not safe (conservative default).
    """
    tags = get_side_effects(fn)
    if not tags:
        return False
    if SideEffect.WRITE in tags or SideEffect.DESTRUCTIVE in tags:
        return False
    return SideEffect.READ in tags


def is_retry_safe(fn: Any) -> bool:
    """Safe to auto-retry on transient error.

    Rules:
      - DESTRUCTIVE → never (caller must opt in per-call).
      - IDEMPOTENT explicitly tagged → safe.
      - READ-only with no WRITE → safe.
      - Otherwise → not safe.
    """
    tags = get_side_effects(fn)
    if not tags:
        return False
    if SideEffect.DESTRUCTIVE in tags:
        return False
    if SideEffect.IDEMPOTENT in tags:
        return True
    if SideEffect.READ in tags and SideEffect.WRITE not in tags:
        return True
    return False


def is_destructive(fn: Any) -> bool:
    """True if the tool has the DESTRUCTIVE tag."""
    return SideEffect.DESTRUCTIVE in get_side_effects(fn)
