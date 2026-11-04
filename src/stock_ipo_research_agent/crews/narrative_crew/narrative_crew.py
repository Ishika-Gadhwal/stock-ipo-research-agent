from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task

from stock_ipo_research_agent.models import Narrative


@CrewBase
class NarrativeCrew:
    """Report writer: no tools. It only turns verified figures into a short summary."""

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def report_writer(self) -> Agent:
        return Agent(
            config=self.agents_config["report_writer"],  # type: ignore[index]
            tools=[],  # WHY: it must not search or read anything, only write
            max_iter=2,
        )

    @task
    def writing_task(self) -> Task:
        return Task(
            config=self.tasks_config["writing_task"],  # type: ignore[index]
            output_pydantic=Narrative,
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
