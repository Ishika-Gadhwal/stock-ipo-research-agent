"""CrewAI tool wrapper: annual report -> cited headline figures."""

from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from stock_ipo_research_agent.tools.financial_facts import get_company, read_facts_for_agent
from stock_ipo_research_agent.tools.search import get_search_client


class FinancialFactsInput(BaseModel):
    report_url: str = Field(
        ...,
        description="URL of the annual report PDF, copied exactly from the search results.",
    )


class FinancialFactsTool(BaseTool):
    name: str = "Annual report figures"
    description: str = (
        "Reads an annual report PDF and returns headline profit and loss figures "
        "(revenue, other income, total income, profit from continuing operations) "
        "with PDF page numbers, units and source lines. The company is already fixed "
        "by the user's confirmation. Only report figures this tool returns, exactly as "
        "shown. If it refuses or says 'could not extract', say the figures were not found."
    )
    args_schema: Type[BaseModel] = FinancialFactsInput

    def _run(self, report_url: str) -> str:
        return read_facts_for_agent(report_url, get_search_client(), get_company())