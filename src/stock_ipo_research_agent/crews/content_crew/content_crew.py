from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task

from stock_ipo_research_agent.models import ReportChoice, SelectedSources
from stock_ipo_research_agent.tools.source_search_tool import SourceSearchTool


@CrewBase
class ContentCrew:
    """Source finder, then report picker. The second task reads the first one's output."""

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
    def report_picker(self) -> Agent:
        return Agent(
            config=self.agents_config["report_picker"],  # type: ignore[index]
            tools=[],  # WHY: it only chooses a URL. Code reads the PDF.
            max_iter=2,
        )

    @task
    def source_discovery_task(self) -> Task:
        return Task(
            config=self.tasks_config["source_discovery_task"],  # type: ignore[index]
            output_pydantic=SelectedSources,
        )

    @task
    def pick_report_task(self) -> Task:
        return Task(
            config=self.tasks_config["pick_report_task"],  # type: ignore[index]
            context=[self.source_discovery_task()],  # WHY: the picker reads the finder's URLs
            output_pydantic=ReportChoice,
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