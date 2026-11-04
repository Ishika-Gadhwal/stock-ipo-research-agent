from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task

from stock_ipo_research_agent.models import AnalystNote, SelectedSources
from stock_ipo_research_agent.tools.financial_facts_tool import FinancialFactsTool
from stock_ipo_research_agent.tools.source_search_tool import SourceSearchTool


@CrewBase
class ContentCrew:
    """Source finder, then financial analyst. The second task reads the first one's output."""

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def company_researcher(self) -> Agent:
        return Agent(
            config=self.agents_config["company_researcher"],  # type: ignore[index]
            tools=[SourceSearchTool()],
            max_iter=5,
        )

    @agent
    def financial_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["financial_analyst"],  # type: ignore[index]
            tools=[FinancialFactsTool()],
            max_iter=4,
        )

    @task
    def source_discovery_task(self) -> Task:
        return Task(
            config=self.tasks_config["source_discovery_task"],  # type: ignore[index]
            output_pydantic=SelectedSources,
        )

    @task
    def analysis_task(self) -> Task:
        return Task(
            config=self.tasks_config["analysis_task"],  # type: ignore[index]
            context=[self.source_discovery_task()],  # WHY: the analyst reads the source finder's URLs
            output_pydantic=AnalystNote,
        )

    @crew
    def crew(self) -> Crew:
        """Creates the Content Crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )