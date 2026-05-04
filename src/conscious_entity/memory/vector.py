from __future__ import annotations

import math
from array import array
from collections.abc import Sequence


def encode_embedding(values: Sequence[float]) -> bytes:
    """Store embeddings as compact float32 bytes in SQLite."""
    return array("f", [float(v) for v in values]).tobytes()


def decode_embedding(blob: bytes | memoryview | None) -> list[float]:
    if not blob:
        return []
    arr = array("f")
    arr.frombytes(bytes(blob))
    return list(arr)


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
