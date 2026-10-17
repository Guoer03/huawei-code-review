"""Adapters for established language checkers.

The adapters deliberately have no dependency on the checker in ``scripts``.  A
caller can run the adapters opportunistically and merge their findings with the
deterministic Huawei rules.  Every result is a JSON-serialisable dictionary,
including the cases where an executable is not installed.
"""

from .runner import (
    ADAPTERS,
    Finding,
    available_adapters,
    parse_output,
    run_adapter,
)

__all__ = ["ADAPTERS", "Finding", "available_adapters", "parse_output", "run_adapter"]
