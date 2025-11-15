"""
TraceStore and NDJSON persistence layer.

Handles thread-safe storage and optional encryption of trace records.
"""

from __future__ import annotations
import atexit
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .tracing import TraceRecord


class TraceStore:
    """
    Thread-safe in-memory store for TraceRecords with periodic NDJSON flush.

    Singleton pattern: use TraceStore.current() to access the global instance.
    """

    _instance: TraceStore | None = None
    _lock = threading.Lock()

    def __init__(self, output_dir: str | Path | None = None, auto_flush_threshold: int = 10):
        """
        Initialize TraceStore.

        Args:
            output_dir: Directory for trace files (default: ./traces)
            auto_flush_threshold: Flush to disk after N records (0 = disable auto-flush)
        """
        self.output_dir = Path(output_dir or os.getenv("SKELETON_TRACE_DIR", "./traces"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.auto_flush_threshold = auto_flush_threshold
        self.records: list[TraceRecord] = []
        self._write_lock = threading.Lock()

        # Generate unique filename for this process
        pid = os.getpid()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.trace_file = self.output_dir / f"trace-{pid}-{timestamp}.ndjson"

        # Register atexit handler to flush on program exit
        atexit.register(self.flush)

    @classmethod
    def current(cls) -> TraceStore:
        """Get or create the global TraceStore instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the global instance (useful for testing)."""
        with cls._lock:
            if cls._instance:
                cls._instance.flush()
            cls._instance = None

    def add(self, record: TraceRecord) -> None:
        """
        Add a TraceRecord to the store.

        Auto-flushes if threshold is reached.
        """
        with self._write_lock:
            self.records.append(record)

            # Auto-flush if threshold reached
            if self.auto_flush_threshold > 0 and len(self.records) >= self.auto_flush_threshold:
                self._flush_unlocked()

    def flush(self) -> None:
        """Flush all records to NDJSON file."""
        with self._write_lock:
            self._flush_unlocked()

    def _flush_unlocked(self) -> None:
        """Internal flush (must be called with _write_lock held)."""
        if not self.records:
            return

        # Write to NDJSON file (append mode)
        with open(self.trace_file, "a", encoding="utf-8") as f:
            for record in self.records:
                json_line = json.dumps(record.to_dict(), ensure_ascii=False)
                f.write(json_line + "\n")

        # Clear records after successful write
        self.records.clear()

    def get_trace_file(self) -> Path:
        """Get the current trace file path."""
        return self.trace_file


def load_trace_records(trace_file: str | Path) -> list[TraceRecord]:
    """
    Load TraceRecords from an NDJSON file.

    Args:
        trace_file: Path to .ndjson trace file

    Returns:
        List of TraceRecord objects
    """
    records = []
    with open(trace_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            records.append(TraceRecord.from_dict(data))
    return records


def load_all_traces(trace_dir: str | Path) -> list[TraceRecord]:
    """
    Load all TraceRecords from all .ndjson files in a directory.

    Args:
        trace_dir: Directory containing trace files

    Returns:
        Combined list of all TraceRecords
    """
    trace_dir = Path(trace_dir)
    all_records = []

    for trace_file in trace_dir.glob("*.ndjson"):
        all_records.extend(load_trace_records(trace_file))

    return all_records
