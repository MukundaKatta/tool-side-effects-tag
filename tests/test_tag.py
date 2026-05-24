"""Tests for tool_side_effects_tag."""

from __future__ import annotations

import pytest

from tool_side_effects_tag import (
    SideEffect,
    TOOL_SIDE_EFFECTS_ATTR,
    get_side_effects,
    has_side_effect,
    is_destructive,
    is_parallel_safe,
    is_retry_safe,
    side_effects,
)


# ---- enum ----------------------------------------------------------------


def test_sideeffect_is_str_enum():
    assert SideEffect.READ.value == "read"
    assert SideEffect.WRITE.value == "write"
    assert SideEffect.IDEMPOTENT.value == "idempotent"
    assert SideEffect.DESTRUCTIVE.value == "destructive"


def test_sideeffect_constructable_from_string():
    assert SideEffect("read") == SideEffect.READ
    with pytest.raises(ValueError):
        SideEffect("nope")


# ---- decorator basics ----------------------------------------------------


def test_decorator_attaches_frozenset():
    @side_effects(SideEffect.READ)
    def f():
        ...

    tags = get_side_effects(f)
    assert isinstance(tags, frozenset)
    assert SideEffect.READ in tags


def test_decorator_attaches_multiple_tags():
    @side_effects(SideEffect.WRITE, SideEffect.IDEMPOTENT)
    def f():
        ...

    assert get_side_effects(f) == frozenset({SideEffect.WRITE, SideEffect.IDEMPOTENT})


def test_decorator_accepts_string_form():
    @side_effects("read", "network")
    def f():
        ...

    assert SideEffect.READ in get_side_effects(f)
    assert SideEffect.NETWORK in get_side_effects(f)


def test_decorator_keeps_opaque_custom_tag():
    @side_effects("custom_tag")
    def f():
        ...

    assert "custom_tag" in get_side_effects(f)


def test_decorator_stacks_unions():
    def f():
        ...

    f = side_effects(SideEffect.READ)(f)
    f = side_effects(SideEffect.NETWORK)(f)
    assert get_side_effects(f) == frozenset({SideEffect.READ, SideEffect.NETWORK})


def test_decorator_rejects_invalid_type():
    with pytest.raises(TypeError):
        side_effects(42)  # type: ignore[arg-type]


def test_get_side_effects_untagged_returns_empty():
    def f():
        ...

    assert get_side_effects(f) == frozenset()


def test_attr_is_documented_constant():
    assert TOOL_SIDE_EFFECTS_ATTR == "__tool_side_effects__"


def test_has_side_effect_helper():
    @side_effects(SideEffect.READ, SideEffect.NETWORK)
    def f():
        ...

    assert has_side_effect(f, SideEffect.READ)
    assert has_side_effect(f, "network")  # str form
    assert not has_side_effect(f, SideEffect.WRITE)


# ---- decorator preserves call behavior ----------------------------------


def test_decorator_preserves_function_call():
    @side_effects(SideEffect.READ)
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


def test_decorator_preserves_metadata():
    @side_effects(SideEffect.READ)
    def my_fn():
        """Docstring."""
        ...

    assert my_fn.__name__ == "my_fn"
    assert "Docstring" in (my_fn.__doc__ or "")


# ---- is_parallel_safe ---------------------------------------------------


def test_parallel_safe_read_only():
    @side_effects(SideEffect.READ)
    def f():
        ...

    assert is_parallel_safe(f) is True


def test_not_parallel_safe_when_writes():
    @side_effects(SideEffect.READ, SideEffect.WRITE)
    def f():
        ...

    assert is_parallel_safe(f) is False


def test_not_parallel_safe_when_destructive():
    @side_effects(SideEffect.READ, SideEffect.DESTRUCTIVE)
    def f():
        ...

    assert is_parallel_safe(f) is False


def test_not_parallel_safe_when_untagged():
    def f():
        ...

    assert is_parallel_safe(f) is False


# ---- is_retry_safe ------------------------------------------------------


def test_retry_safe_idempotent():
    @side_effects(SideEffect.WRITE, SideEffect.IDEMPOTENT)
    def f():
        ...

    assert is_retry_safe(f) is True


def test_retry_safe_read_only():
    @side_effects(SideEffect.READ)
    def f():
        ...

    assert is_retry_safe(f) is True


def test_not_retry_safe_when_destructive_even_with_idempotent():
    @side_effects(SideEffect.DESTRUCTIVE, SideEffect.IDEMPOTENT)
    def f():
        ...

    assert is_retry_safe(f) is False


def test_not_retry_safe_external_without_idempotent():
    @side_effects(SideEffect.EXTERNAL)
    def f():
        ...

    assert is_retry_safe(f) is False


def test_retry_safe_external_with_idempotent():
    @side_effects(SideEffect.EXTERNAL, SideEffect.IDEMPOTENT)
    def f():
        ...

    assert is_retry_safe(f) is True


def test_not_retry_safe_untagged():
    def f():
        ...

    assert is_retry_safe(f) is False


# ---- is_destructive -----------------------------------------------------


def test_is_destructive_returns_true_when_tagged():
    @side_effects(SideEffect.DESTRUCTIVE)
    def f():
        ...

    assert is_destructive(f) is True


def test_is_destructive_false_otherwise():
    @side_effects(SideEffect.WRITE)
    def f():
        ...

    assert is_destructive(f) is False
