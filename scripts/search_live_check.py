from dotenv import load_dotenv

load_dotenv()

from stock_ipo_research_agent.tools.search import SearchClient, format_results

client = SearchClient(max_results=5)
results = client.search("Tata Motors Passenger Vehicles annual report 2025-26 nseindia")
print(format_results(results))
print()
print("URLs remembered by the client:", len(client.seen_urls))