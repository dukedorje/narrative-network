"""Bittensor availability detection and compatibility helpers.

This module is the single source of truth for whether bittensor is installed.
It MUST remain self-contained — only import stdlib and bittensor (conditionally).
"""

from __future__ import annotations

import logging as _stdlib_logging

try:
    import bittensor as bt

    _BT_AVAILABLE = True
except ImportError:
    _BT_AVAILABLE = False
    bt = None  # type: ignore


def get_protocol_module():
    """Return the appropriate protocol module based on bittensor availability."""
    if _BT_AVAILABLE:
        from subnet import protocol

        return protocol
    else:
        from subnet import protocol_local

        return protocol_local


def get_logger(name: str):
    """Return bt.logging if available, else stdlib logger."""
    if _BT_AVAILABLE:
        return bt.logging  # type: ignore[union-attr]
    return _stdlib_logging.getLogger(name)
