from fastapi import FastAPI
import time
import datetime

app = FastAPI()

# Rate limiting variables
REQUEST_LOG = []
RATE_LIMIT = 5
TIME_WINDOW = 10

# In-memory storage
incidents = {}

# Allowed state transitions
ALLOWED_TRANSITIONS = {
    "OPEN": ["INVESTIGATING"],
    "INVESTIGATING": ["RESOLVED"],
    "RESOLVED": ["CLOSED"]
}


@app.get("/")
async def home():
    return {"message": "IMS running"}


# 🔹 Rate Limiter
def is_rate_limited():
    current = time.time()

    # Remove old requests
    while REQUEST_LOG and REQUEST_LOG[0] < current - TIME_WINDOW:
        REQUEST_LOG.pop(0)

    if len(REQUEST_LOG) >= RATE_LIMIT:
        return True

    REQUEST_LOG.append(current)
    return False


# 🔹 Ingest signals
@app.post("/ingest")
async def ingest(signal: dict):

    # Rate limiting check
    if is_rate_limited():
        return {"error": "Too many requests, slow down"}

    comp = signal["component_id"]

    if comp not in incidents:
        current_time = time.time()

        incidents[comp] = {
            "status": "OPEN",
            "signals": [],
            "start_time": datetime.datetime.fromtimestamp(current_time).strftime("%Y-%m-%d %H:%M:%S"),
            "start_time_raw": current_time
        }

    incidents[comp]["signals"].append(signal)

    return {"status": "processed"}


# 🔹 Get all incidents
@app.get("/incidents")
async def get_incidents():
    return incidents


# 🔹 Update status (with transition validation)
@app.put("/incident/{id}")
async def update_status(id: str, status: str):
    if id not in incidents:
        return {"error": "Incident not found"}

    current = incidents[id]["status"]

    if status not in ALLOWED_TRANSITIONS.get(current, []):
        return {"error": f"Invalid transition from {current} to {status}"}

    incidents[id]["status"] = status
    return {"updated": True}


# 🔹 Close incident (only if RESOLVED + RCA required)
@app.post("/incident/{id}/close")
async def close_incident(id: str, rca: str):
    if id not in incidents:
        return {"error": "Incident not found"}

    if not rca:
        return {"error": "RCA required"}

    # Enforce lifecycle
    if incidents[id]["status"] != "RESOLVED":
        return {"error": "Must be RESOLVED before closing"}

    incidents[id]["status"] = "CLOSED"
    incidents[id]["rca"] = rca

    current_time = time.time()

    incidents[id]["end_time"] = datetime.datetime.fromtimestamp(current_time).strftime("%Y-%m-%d %H:%M:%S")
    incidents[id]["end_time_raw"] = current_time

    # MTTR calculation
    incidents[id]["mttr"] = round(
        incidents[id]["end_time_raw"] - incidents[id]["start_time_raw"], 2
    )

    return {"closed": True}


# 🔹 Health check
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "incidents_count": len(incidents)
    }