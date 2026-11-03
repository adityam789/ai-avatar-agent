"""Base collector interface."""
from abc import ABC, abstractmethod
from typing import List
from ai_avatar.research.schemas import RawSnippet


class SourceCollector(ABC):

    @abstractmethod
    def collect(self, topic: str) -> List[RawSnippet]:
        pass

