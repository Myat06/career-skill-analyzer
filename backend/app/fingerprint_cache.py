"""Generic in-process cache keyed by a content fingerprint, capped to a
maximum size with LRU eviction. Shared by app/scoring/gap_engine.py's
skill-gap match cache and app/reporting/consultation.py's consultation-build
cache -- both independently hand-rolled the identical OrderedDict
get/move-to-end/evict-while-oversize dance before being consolidated here.
"""

from collections import OrderedDict
from typing import Generic, TypeVar

V = TypeVar("V")


class FingerprintCache(Generic[V]):
    def __init__(self, maxsize: int):
        self._maxsize = maxsize
        self._data: OrderedDict[str, V] = OrderedDict()

    def get(self, key: str) -> V | None:
        value = self._data.get(key)
        if value is not None:
            self._data.move_to_end(key)
        return value

    def set(self, key: str, value: V) -> None:
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)
