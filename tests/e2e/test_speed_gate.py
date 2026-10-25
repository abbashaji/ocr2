"""Speed gate: the clean sample must be recognised in <= 10 s on 2 CPUs."""

from __future__ import annotations

import os
import time

import pytest

from matnyab.api import OcrOptions

pytestmark = pytest.mark.slow

LIMIT_S = 10.0
CPUS = 2


@pytest.fixture
def two_cpus():
    """Pin the process to 2 CPUs when more are available (Linux); yields the CPU count in use.

    With fewer than 2 CPUs nothing can be pinned; ``test_clean_sample_within_budget``
    then scales the limit (the work is 147+ independent Tesseract calls, CPU bound).
    """
    if not hasattr(os, "sched_getaffinity"):
        yield os.cpu_count() or 1
        return
    original = os.sched_getaffinity(0)
    if len(original) > CPUS:
        os.sched_setaffinity(0, set(sorted(original)[:CPUS]))
    try:
        yield len(os.sched_getaffinity(0))
    finally:
        os.sched_setaffinity(0, original)


def test_clean_sample_within_budget(engine, clean_path, two_cpus):
    # No warm-up on purpose: a user's first image pays for a cold start too.
    # Default OcrOptions: the engine picks its own worker count, as the app does.
    t0 = time.perf_counter()
    res = engine.recognize(clean_path, OcrOptions(mode="auto"))
    wall = time.perf_counter() - t0
    print(f"SPEED client_clean.png: wall {wall:.2f}s, engine {res.elapsed_s:.2f}s, cpus in use={two_cpus}")
    assert res.text.strip()
    # >= 2 CPUs: the limit is exactly LIMIT_S. On a 1-CPU machine the same CPU-bound work
    # takes about twice as long, so the limit is scaled by CPUS / cpus_in_use.
    limit = LIMIT_S * max(1.0, CPUS / max(1, two_cpus))
    assert wall <= limit, f"{wall:.2f}s > {limit:.1f}s (cpus in use: {two_cpus})"
