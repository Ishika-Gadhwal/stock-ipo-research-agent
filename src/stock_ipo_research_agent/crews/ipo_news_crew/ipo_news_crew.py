from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task

from stock_ipo_research_agent.models import IpoView
from stock_ipo_research_agent.tools.source_search_tool import SourceSearchTool


@CrewBase
class IpoNewsCrew:
    """IPO path: recent news in, pros/cons and a cautious lean out. Output is UNVERIFIED."""

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def ipo_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["ipo_analyst"],  # type: ignore[index]
            tools=[SourceSearchTool()],
            max_iter=5,
        )

    @task
    def ipo_news_task(self) -> Task:
        return Task(
            config=self.tasks_config["ipo_news_task"],  # type: ignore[index]
            output_pydantic=IpoView,
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
