"""Data schemas for the research agent.

Small, dependency-free data shapes used within the research package.
"""
from dataclasses import dataclass
from typing import Dict, List, Literal

@dataclass
class RawSnippet:
    source: str
    title: str
    text: str
    metadata: Dict

@dataclass
class ResearchBundle:
    topic: str
    facts: List[str]
    freshness: Literal["cached", "fresh"]
    sources: List[str]


