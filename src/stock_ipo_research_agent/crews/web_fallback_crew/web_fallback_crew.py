from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task

from stock_ipo_research_agent.models import WebSummary
from stock_ipo_research_agent.tools.source_search_tool import SourceSearchTool


@CrewBase
class WebFallbackCrew:
    """Used only when code could not read the annual report. Its output is UNVERIFIED."""

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def web_researcher(self) -> Agent:
        return Agent(
            config=self.agents_config["web_researcher"],  # type: ignore[index]
            tools=[SourceSearchTool()],
            max_iter=4,
        )

    @task
    def web_research_task(self) -> Task:
        return Task(
            config=self.tasks_config["web_research_task"],  # type: ignore[index]
            output_pydantic=WebSummary,
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
