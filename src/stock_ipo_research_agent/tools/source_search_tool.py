"""CrewAI tool wrapper around SearchClient."""

from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from stock_ipo_research_agent.tools.search import (
    SearchError,
    format_results,
    get_search_client,
)


class SourceSearchInput(BaseModel):
    query: str = Field(..., description="The web search query.")


class SourceSearchTool(BaseTool):
    name: str = "Source search"
    description: str = (
        "Searches the web and returns results with title, URL, date and a source type "
        "(official or unverified). Only URLs listed in the results may be cited. "
        "If a field says 'not stated', report it as not stated."
    )
    args_schema: Type[BaseModel] = SourceSearchInput

    def _run(self, query: str) -> str:
        try:
            return format_results(get_search_client().search(query))
        except SearchError as error:
            return f"Search failed: {error}. Do not guess; report that the search failed."