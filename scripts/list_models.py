from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client()  # reads GEMINI_API_KEY from the environment

for model in client.models.list():
    if "flash" in model.name.lower():
        print(model.name)