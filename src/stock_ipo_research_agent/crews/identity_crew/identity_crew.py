from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import SerperDevTool

from stock_ipo_research_agent.models import IdentityResult


@CrewBase
class IdentityCrew:
    """Finds which legal entities a company name could refer to"""

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def identity_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["identity_analyst"],  # type: ignore[index]
            tools=[SerperDevTool(n_results=5)],
            max_iter=6,
        )

    @task
    def identify_company_task(self) -> Task:
        return Task(
            config=self.tasks_config["identify_company_task"],  # type: ignore[index]
            output_pydantic=IdentityResult,
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )