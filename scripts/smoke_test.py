from dotenv import load_dotenv
from crewai import LLM

load_dotenv()

llm = LLM(model="gemini/gemini-3.1-flash-lite", temperature=0.2)

response = llm.call("In one sentence, what is an IPO?")
print(response)