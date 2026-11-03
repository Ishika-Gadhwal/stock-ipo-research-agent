from dotenv import load_dotenv
from crewai_tools import SerperDevTool

load_dotenv()

tool = SerperDevTool(n_results=3)
print(tool.run(search_query="Tata Motors annual report investor relations"))