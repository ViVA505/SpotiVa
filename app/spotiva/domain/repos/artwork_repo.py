from __future__ import annotations

from abc import ABC, abstractmethod


class ArtworkRepository(ABC):
    @abstractmethod
    def resolve_artwork_url(self, item_url: str) -> str:
        raise NotImplementedError
