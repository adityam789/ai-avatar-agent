"""Google CSE (Custom Search) collector stub.
"""
import os
import requests
from typing import List
from ..schemas import RawSnippet
from .base import SourceCollector

class GoogleCSECollector(SourceCollector):

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.cse_id = os.getenv("GOOGLE_CSE_ID")

    def collect(self, topic: str) -> List[RawSnippet]:
        params = {
            "key": self.api_key,
            "cx": self.cse_id,
            "q": topic,
            "num": 5
        }

        resp = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params=params,
            timeout=10
        )
        data = resp.json()

        snippets = []
        for item in data.get("items", []):
            snippets.append(
                RawSnippet(
                    source="google_cse",
                    title=item["title"],
                    text=item.get("snippet", ""),
                    metadata={
                        "url": item.get("link"),
                        "displayLink": item.get("displayLink")
                    }
                )
            )

        return snippets

