from __future__ import annotations

import threading
from pathlib import Path
from queue import Queue

from conscious_entity.db.connection import get_connection


def test_connection_can_be_shared_across_threads_when_opted_in(tmp_path: Path):
    db_path = tmp_path / "memory.db"
    conn = get_connection(db_path, check_same_thread=False)
    conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
    conn.commit()

    results: Queue[object] = Queue()

    def worker() -> None:
        try:
            conn.execute("INSERT INTO sample (value) VALUES (?)", ("thread-ok",))
            conn.commit()
            row = conn.execute("SELECT value FROM sample LIMIT 1").fetchone()
            results.put(row["value"] if row is not None else None)
        except Exception as exc:  # pragma: no cover - surfaced via assertion
            results.put(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    result = results.get_nowait()
    assert result == "thread-ok"
    conn.close()
