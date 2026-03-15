"""Metagraph watcher — async background poller for miner registration events.

MetagraphWatcher polls bt.Subtensor on a configurable interval, detects new
registrations and deregistrations, and maintains a thread-safe AxonCache that
other components can query without hitting the chain.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field

import bittensor as bt

from subnet import NETUID

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RegistrationEvent:
    """Emitted when a miner registers or deregisters."""

    uid: int
    axon_info: bt.AxonInfo
    event_type: str          # "registered" | "deregistered"
    block: int
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Thread-safe axon cache
# ---------------------------------------------------------------------------

class AxonCache:
    """Thread-safe snapshot of the current metagraph axon info.

    Callers read from this cache without hitting the chain.
    MetagraphWatcher writes to it atomically after each poll.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # uid -> AxonInfo
        self._axons: dict[int, bt.AxonInfo] = {}
        self._last_updated: float = 0.0
        self._last_block: int = 0

    def update(self, axons: dict[int, bt.AxonInfo], block: int) -> None:
        """Atomically replace the cache with a new snapshot."""
        with self._lock:
            self._axons = dict(axons)
            self._last_updated = time.time()
            self._last_block = block

    def get(self, uid: int) -> bt.AxonInfo | None:
        with self._lock:
            return self._axons.get(uid)

    def all(self) -> dict[int, bt.AxonInfo]:
        with self._lock:
            return dict(self._axons)

    def uids(self) -> list[int]:
        with self._lock:
            return list(self._axons.keys())

    @property
    def last_block(self) -> int:
        return self._last_block

    @property
    def last_updated(self) -> float:
        return self._last_updated

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._axons)


# ---------------------------------------------------------------------------
# Metagraph watcher
# ---------------------------------------------------------------------------

class MetagraphWatcher:
    """Async background poller that keeps AxonCache in sync with the chain.

    Usage::

        watcher = MetagraphWatcher(subtensor, netuid=NETUID)
        await watcher.start()
        axon = watcher.cache.get(uid)
        ...
        await watcher.stop()

    Registration event callbacks receive a RegistrationEvent and can be
    registered via ``add_listener(callback)``.  Callbacks are invoked
    in the polling loop (not in a separate thread), so they should be
    fast and non-blocking.
    """

    def __init__(
        self,
        subtensor: bt.Subtensor,
        netuid: int = NETUID,
        poll_interval_s: float = 12.0,
    ) -> None:
        self._subtensor = subtensor
        self._netuid = netuid
        self._poll_interval = poll_interval_s

        self.cache = AxonCache()
        self._listeners: list = []
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None

    def add_listener(self, callback) -> None:
        """Register a callback(event: RegistrationEvent) -> None."""
        self._listeners.append(callback)

    def _notify(self, event: RegistrationEvent) -> None:
        for cb in self._listeners:
            try:
                cb(event)
            except Exception as exc:
                logger.warning("Listener %s raised: %s", cb, exc)

    async def _poll_once(self) -> None:
        """Fetch metagraph and update cache; emit registration events."""
        try:
            metagraph: bt.metagraph = self._subtensor.metagraph(self._netuid)
            block: int = metagraph.block.item() if hasattr(metagraph.block, "item") else int(metagraph.block)

            new_axons: dict[int, bt.AxonInfo] = {
                int(uid): axon
                for uid, axon in zip(metagraph.uids.tolist(), metagraph.axons)
            }

            old_uids = set(self.cache.uids())
            new_uids = set(new_axons.keys())

            for uid in new_uids - old_uids:
                self._notify(
                    RegistrationEvent(
                        uid=uid,
                        axon_info=new_axons[uid],
                        event_type="registered",
                        block=block,
                    )
                )
                logger.info("Miner registered: uid=%d block=%d", uid, block)

            for uid in old_uids - new_uids:
                self._notify(
                    RegistrationEvent(
                        uid=uid,
                        axon_info=self.cache.get(uid),  # type: ignore[arg-type]
                        event_type="deregistered",
                        block=block,
                    )
                )
                logger.info("Miner deregistered: uid=%d block=%d", uid, block)

            self.cache.update(new_axons, block)
            logger.debug(
                "Metagraph polled: block=%d miners=%d", block, len(new_axons)
            )
        except Exception as exc:
            logger.error("MetagraphWatcher poll failed: %s", exc, exc_info=True)

    async def _loop(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            await self._poll_once()
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._poll_interval
                )
            except asyncio.TimeoutError:
                pass  # normal — keep polling

    async def start(self) -> None:
        """Start the background polling loop."""
        if self._task is not None and not self._task.done():
            logger.warning("MetagraphWatcher already running")
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._loop(), name="metagraph-watcher")
        logger.info(
            "MetagraphWatcher started (netuid=%d, interval=%.1fs)",
            self._netuid,
            self._poll_interval,
        )

    async def stop(self) -> None:
        """Signal the polling loop to stop and wait for it to finish."""
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=self._poll_interval + 5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        logger.info("MetagraphWatcher stopped")
