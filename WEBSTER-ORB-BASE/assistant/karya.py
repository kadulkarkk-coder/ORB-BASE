"""Karya: internal background-task coordination for WEBSTER.

Karya manages trusted in-process callables only. It is not the G5 Actions
system: it does not discover plugins, load files, or execute AI-generated code.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid

from collections import OrderedDict
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATES = {
    TaskState.SUCCEEDED,
    TaskState.FAILED,
    TaskState.CANCELLED,
}


@dataclass(frozen=True)
class TaskInfo:
    task_id: str
    name: str
    state: TaskState
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    cancellation_requested: bool = False


class TaskSignals(QObject):
    """Signals emitted by a Karya-managed worker."""

    started = Signal(str)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal(str)


class TaskHandle:
    """Stable reference to a submitted task."""

    def __init__(
        self,
        coordinator: "Karya",
        task_id: str,
        signals: TaskSignals,
        runnable: QRunnable,
        priority: int,
    ):
        self._coordinator = coordinator
        self.task_id = task_id
        self.signals = signals
        self._runnable = runnable
        self._priority = priority
        self._started = False
        self._start_lock = threading.Lock()

    def start(self) -> bool:
        """Start a prepared task exactly once.

        Callers may connect result signals before starting to avoid losing
        very fast task completions.
        """
        with self._start_lock:
            if self._started:
                return False
            self._started = True
        self._coordinator._enqueue(
            self._runnable,
            self._priority,
            self.signals,
            self.task_id,
        )
        return True

    @property
    def info(self) -> TaskInfo | None:
        return self._coordinator.get(self.task_id)

    @property
    def state(self) -> TaskState | None:
        info = self.info
        return info.state if info else None

    def cancel(self) -> bool:
        """Request cancellation.

        Queued work is skipped when its worker reaches the queue head.
        Running Python callables cannot be forcibly interrupted; they must
        implement their own cooperative cancellation if that is required.
        """
        return self._coordinator.cancel(self.task_id)


class _ManagedRunnable(QRunnable):
    def __init__(
        self,
        coordinator: "Karya",
        task_id: str,
        function: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        cancel_event: threading.Event,
        signals: TaskSignals,
    ):
        super().__init__()
        self._coordinator = coordinator
        self._task_id = task_id
        self._function = function
        self._args = args
        self._kwargs = kwargs
        self._cancel_event = cancel_event
        self._signals = signals

    @Slot()
    def run(self) -> None:
        if self._cancel_event.is_set() or not self._coordinator._start(
            self._task_id,
            self._cancel_event,
        ):
            self._coordinator._finish(
                self._task_id,
                TaskState.CANCELLED,
            )
            self._signals.cancelled.emit(self._task_id)
            return

        self._signals.started.emit(self._task_id)

        try:
            result = self._function(*self._args, **self._kwargs)
        except Exception as exc:
            logger.exception("Karya task %s failed", self._task_id)
            self._coordinator._finish(
                self._task_id,
                TaskState.FAILED,
                error=str(exc),
            )
            self._signals.failed.emit(str(exc))
            return

        self._coordinator._finish(self._task_id, TaskState.SUCCEEDED)
        self._signals.finished.emit(result)


class Karya:
    """Thread-safe task registry and submission layer over QThreadPool."""

    def __init__(
        self,
        pool: QThreadPool | None = None,
        history_limit: int = 100,
    ):
        self.pool = pool or QThreadPool.globalInstance()
        self.history_limit = max(1, int(history_limit))
        self._lock = threading.RLock()
        self._records: OrderedDict[str, TaskInfo] = OrderedDict()
        self._cancel_events: dict[str, threading.Event] = {}

    def submit(
        self,
        function: Callable[..., Any],
        *args: Any,
        task_name: str | None = None,
        priority: int = 0,
        auto_start: bool = True,
        **kwargs: Any,
    ) -> TaskHandle:
        """Queue a trusted callable and return its task handle."""
        if not callable(function):
            raise TypeError("Karya tasks must be callable.")

        task_id = f"task-{uuid.uuid4().hex[:10]}"
        name = task_name or getattr(function, "__name__", "background-task")
        now = time.time()
        cancel_event = threading.Event()
        signals = TaskSignals()

        with self._lock:
            self._records[task_id] = TaskInfo(
                task_id=task_id,
                name=str(name),
                state=TaskState.QUEUED,
                created_at=now,
            )
            self._cancel_events[task_id] = cancel_event
            self._prune_locked()

        runnable = _ManagedRunnable(
            self,
            task_id,
            function,
            args,
            kwargs,
            cancel_event,
            signals,
        )
        handle = TaskHandle(
            self,
            task_id,
            signals,
            runnable,
            int(priority),
        )
        if auto_start:
            handle.start()
        return handle

    def _enqueue(
        self,
        runnable: QRunnable,
        priority: int,
        signals: TaskSignals,
        task_id: str,
    ) -> None:
        try:
            self.pool.start(runnable, priority)
        except Exception as exc:
            logger.exception("Could not enqueue Karya task %s", task_id)
            self._finish(task_id, TaskState.FAILED, error=str(exc))
            signals.failed.emit(str(exc))

    def get(self, task_id: str) -> TaskInfo | None:
        with self._lock:
            return self._records.get(task_id)

    def list_tasks(self, limit: int | None = None) -> list[TaskInfo]:
        with self._lock:
            records = list(self._records.values())
        if limit is not None:
            records = records[-max(0, int(limit)):] if limit else []
        return records

    @property
    def active_count(self) -> int:
        with self._lock:
            return sum(
                info.state not in _TERMINAL_STATES
                for info in self._records.values()
            )

    def cancel(self, task_id: str) -> bool:
        """Request cancellation for queued or running work."""
        with self._lock:
            info = self._records.get(task_id)
            event = self._cancel_events.get(task_id)
            if info is None or event is None or info.state in _TERMINAL_STATES:
                return False
            event.set()
            self._records[task_id] = replace(
                info,
                cancellation_requested=True,
            )
            return True

    def cancel_all(self) -> int:
        """Request cancellation for every non-terminal task."""
        with self._lock:
            task_ids = [
                task_id
                for task_id, info in self._records.items()
                if info.state not in _TERMINAL_STATES
            ]
        return sum(self.cancel(task_id) for task_id in task_ids)

    def _start(
        self,
        task_id: str,
        cancel_event: threading.Event,
    ) -> bool:
        with self._lock:
            info = self._records.get(task_id)
            if info is None or info.state in _TERMINAL_STATES:
                return False
            if cancel_event.is_set():
                return False
            self._records[task_id] = replace(
                info,
                state=TaskState.RUNNING,
                started_at=time.time(),
            )
            return True

    def _finish(
        self,
        task_id: str,
        state: TaskState,
        error: str | None = None,
    ) -> None:
        with self._lock:
            info = self._records.get(task_id)
            if info is None:
                return
            self._records[task_id] = replace(
                info,
                state=state,
                finished_at=time.time(),
                error=error,
            )
            self._cancel_events.pop(task_id, None)
            self._prune_locked()

    def _prune_locked(self) -> None:
        while len(self._records) > self.history_limit:
            removable = next(
                (
                    task_id
                    for task_id, info in self._records.items()
                    if info.state in _TERMINAL_STATES
                ),
                None,
            )
            if removable is None:
                break
            self._records.pop(removable, None)
            self._cancel_events.pop(removable, None)
