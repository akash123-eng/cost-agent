import json
import datetime
import azure.functions as func

from langgraph.graph import StateGraph
from langchain_openai import AzureChatOpenAI
from azure.storage.blob import BlobServiceClient

# =========================================================
# 🔧 CONFIGURATION (NO ENV VARIABLES)
# =========================================================

# Azure OpenAI
AZURE_OPENAI_ENDPOINT = "https://<AZURE_OPENAI_DEPLOYMENT_ENDPOINT>.cognitiveservices.azure.com/"
AZURE_OPENAI_API_KEY = "<AZURE_OPENAI_API_KEY>"
AZURE_OPENAI_DEPLOYMENT = "gpt-4o-mini"
AZURE_OPENAI_API_VERSION = "2024-12-01-preview"

# Azure Blob Storage
AZURE_STORAGE_CONNECTION_STRING = (
    "DefaultEndpointsProtocol=https;"
    "AccountName=<AZURE_STORAGE_ACCOUNT_NAME>;"
    "AccountKey=<AZURE_STORAGE_ACCOUNT_ACCESS_KEY>;"
    "EndpointSuffix=core.windows.net"
)
BLOB_CONTAINER_NAME = "agent-state"

# =========================================================
# 🧠 LANGGRAPH NODES
# =========================================================

def fetch_cost_data(state: dict) -> dict:
    """
    Simulated cost fetch (free-tier safe).
    Replace with Cost Management API later if needed.
    """
    state["cost_data"] = {
        "resource": "Azure Storage Account",
        "monthly_cost_usd": 2.35,
        "currency": "USD"
    }
    return state


def detect_anomaly(state: dict) -> dict:
    """
    Simple anomaly detection logic.
    """
    cost = state["cost_data"]["monthly_cost_usd"]
    state["anomaly_detected"] = cost > 5
    return state


def simulate_optimizations(state: dict) -> dict:
    llm = AzureChatOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        deployment_name=AZURE_OPENAI_DEPLOYMENT,
        api_version=AZURE_OPENAI_API_VERSION,
        temperature=0.1,
        max_tokens=400
    )

    user_question = state.get("user_question", "Explore my Azure costs")

    prompt = f"""
You are an Azure cost optimization assistant.

Cost data:
{state['cost_data']}

User question:
{user_question}

STRICTLY return a single valid JSON object with the keys:
- resource
- recommended_change
- estimated_monthly_savings
- risk_level
"""

    response = llm.invoke(prompt)

    # --- Safely parse JSON ---
    raw_text = getattr(response, "content", str(response))
    print("📝 Raw LLM output:", raw_text)

    try:
        state["optimizations"] = json.loads(raw_text)
    except json.JSONDecodeError:
        state["optimizations"] = {"raw_output": raw_text}

    return state


def generate_report(state: dict) -> dict:
    """
    Final report node.
    """
    return {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "cost_data": state.get("cost_data"),
        "anomaly_detected": state.get("anomaly_detected"),
        "optimizations": state.get("optimizations")
    }


# =========================================================
# 🪣 AZURE BLOB STORAGE
# =========================================================

def save_state_to_blob(report: dict) -> None:
    """
    Saves agent output to Azure Blob Storage.
    """
    blob_service = BlobServiceClient.from_connection_string(
        AZURE_STORAGE_CONNECTION_STRING
    )

    container_client = blob_service.get_container_client(BLOB_CONTAINER_NAME)

    blob_name = f"agent-report-{datetime.datetime.utcnow().isoformat()}.json"

    container_client.upload_blob(
        name=blob_name,
        data=json.dumps(report, indent=2),
        overwrite=True
    )


# =========================================================
# 🚀 AZURE FUNCTION ENTRYPOINT
# =========================================================

#def main(req: func.HttpRequest) -> func.HttpResponse:
#    user_question = req.params.get(
#        "question",
#        "Explore my Azure costs"
#    )

def main(req: func.HttpRequest) -> func.HttpResponse:
    print("🔥 LangGraph agent invoked")

    user_question = req.params.get(
        "question",
        "Explore my Azure costs"
    )

    graph = StateGraph(dict)

    graph.add_node("fetch_cost", fetch_cost_data)
    graph.add_node("detect_anomaly", detect_anomaly)
    graph.add_node("optimize", simulate_optimizations)
    graph.add_node("report", generate_report)

    graph.set_entry_point("fetch_cost")
    graph.add_edge("fetch_cost", "detect_anomaly")
    graph.add_edge("detect_anomaly", "optimize")
    graph.add_edge("optimize", "report")

    app = graph.compile()

    result = app.invoke({
        "user_question": user_question
    })

    save_state_to_blob(result)

    return func.HttpResponse(
        json.dumps(result, indent=2),
        mimetype="application/json"
    )
