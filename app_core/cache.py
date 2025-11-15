"""Lightweight helpers around Streamlit cache decorators with namespace-aware clearing."""
from __future__ import annotations

from collections import defaultdict
from functools import wraps
from typing import Any, Callable, DefaultDict, ParamSpec, TypeVar

import streamlit as st

P = ParamSpec("P")
T = TypeVar("T")

_CACHE_REGISTRY: DefaultDict[str, list[Callable[[], None]]] = defaultdict(list)


def cache_data(namespace: str, **cache_kwargs: Any) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Wraps st.cache_data but keeps track of each cached function under a namespace.
    That lets us invalidate only the data we need instead of nuking the entire cache.
    """

    if not namespace:
        raise ValueError("cache namespace must be a non-empty string")

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        cached_func = st.cache_data(**cache_kwargs)(func)
        clear_fn = getattr(cached_func, "clear", None)
        if callable(clear_fn):
            _CACHE_REGISTRY[namespace].append(clear_fn)

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return cached_func(*args, **kwargs)

        # expose clear passthrough for finer-grain manual invalidation if needed
        setattr(wrapper, "clear", getattr(cached_func, "clear", lambda: None))
        setattr(wrapper, "_cache_namespace", namespace)
        return wrapper

    return decorator


def clear_cache(namespace: str | None = None) -> None:
    """
    Clears every cached function registered under `namespace`.
    When namespace is None, clears all known caches (still scoped, not Streamlit-global).
    """

    if namespace is None:
        targets = list(_CACHE_REGISTRY.values())
    else:
        targets = [_CACHE_REGISTRY.get(namespace, [])]

    for group in targets:
        for clear_fn in group:
            try:
                clear_fn()
            except Exception:
                # cache clearing should never break the UI; swallow and continue
                continue
