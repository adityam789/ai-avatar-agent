"""Base collector interface."""
from abc import ABC, abstractmethod
from typing import List
from ..schemas import RawSnippet


class SourceCollector(ABC):

    @abstractmethod
    def collect(self, topic: str) -> List[RawSnippet]:
        pass

