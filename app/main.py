import os
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any

import certifi
os.environ["SSL_CERT_FILE"] = certifi.where()

# Ensure root folder is in python path for absolute imports
sys.path.append(str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.agents.graph import agent_app
from app.db.vectordb import vector_db
from app.services.ocr import process_passport_image
from app.db.history import save_chat, get_history

load_dotenv()

app = FastAPI(title="TravelAgent AI API", version="2.0")

origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://travelagent-v2.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PlanRequest(BaseModel):
    user_id: str
    prompt: str
    budget_inr: float
    origin: Optional[str] = "NAG"
    destination: Optional[str] = "BOM"
    from_date: Optional[str] = None       # e.g., "2026-09-10"
    to_date: Optional[str] = None         # e.g., "2026-09-15"
    duration_days: Optional[int] = 3
    trip_type: Optional[str] = Field(default="round_trip")
    preferred_transit: Optional[List[str]] = Field(default=["flight", "train", "bus"])
    include_local_cab: Optional[bool] = True
    include_hotel: Optional[bool] = True
    selected_flight_index: Optional[int] = 0
    selected_hotel_index: Optional[int] = 0
    passport_verified: Optional[bool] = False
    passport_data: Optional[Dict[str, Any]] = {}


class CustomPackageRecalculateRequest(BaseModel):
    flight_price: float = 0.0
    hotel_price_per_night: float = 0.0
    duration_days: int = 3
    trip_type: str = "round_trip"
    include_local_cab: bool = True
    daily_cab_rate: float = 2200.0


@app.get("/", include_in_schema=False)
async def root_redirect():
    """Redirect root path to interactive OpenAPI documentation."""
    return RedirectResponse(url="/docs")


@app.post("/api/v1/plan")
async def generative_plan(req: PlanRequest):
    vector_db.add_user_preference(req.user_id, req.prompt)

    initial_state = {
        "user_id": req.user_id,
        "user_input": req.prompt,
        "total_budget_inr": req.budget_inr,
        "origin": req.origin,
        "destination": req.destination,
        "from_date": req.from_date,
        "to_date": req.to_date,
        "duration_days": req.duration_days,
        "trip_type": req.trip_type,
        "preferred_transit": req.preferred_transit,
        "include_local_cab": req.include_local_cab,
        "include_hotel": req.include_hotel,
        "selected_flight_index": req.selected_flight_index,
        "selected_hotel_index": req.selected_hotel_index,
        "passport_verified": req.passport_verified,
        "passport_data": req.passport_data,
        "is_international": False,
        "requires_passport_ocr": False,
        "retrived_memory": [],
        "retrived_knowledge": [],
        "flight_options": [],
        "train_options": [],
        "bus_options": [],
        "local_cab": {},
        "hotels_options": [],
        "calculated_cost_inr": 0.0,
        "draft_itinerary": "",
    }

    config = {"configurable": {"thread_id": f"thread_{req.user_id}"}}
    result = agent_app.invoke(initial_state, config=config)

    itinerary = result.get("draft_itinerary", "")
    estimated_cost = result.get("calculated_cost_inr", 0.0)

    save_chat(
        user_id=req.user_id,
        origin=result.get("origin", req.origin),
        destination=result.get("destination", req.destination),
        from_date=result.get("from_date", req.from_date),
        to_date=result.get("to_date", req.to_date),
        duration_days=result.get("duration_days", req.duration_days),
        cost=estimated_cost
    )

    # In main.py generative_plan response:
    return {
        "status": "Success",
        "is_international": result.get("is_international", False),
        "requires_passport_ocr": result.get("requires_passport_ocr", False),
        "passport_verified": result.get("passport_verified", False),
        "passport_details": result.get("passport_details", {}),
        "itinerary": itinerary,
        "estimated_cost_inr": estimated_cost,
        "breakdown": {
            "flights": result.get("flight_options", []),
            "trains": result.get("train_options", []),
            "buses": result.get("bus_options", []),
            "cabs": result.get("local_cab", {}),
            "local_cabs": result.get("local_cab", {}),
            "hotels": result.get("hotels_options", []), # Standardized to hotels_options
        },
    }


@app.post("/api/v1/package/recalculate")
async def recalculate_package(req: CustomPackageRecalculateRequest):
    """SaaS Custom Package Dynamic Price Engine"""
    flights_total = req.flight_price * (2 if req.trip_type == "round_trip" else 1)
    nights = max(1, req.duration_days - 1)
    hotels_total = req.hotel_price_per_night * nights
    cabs_total = (req.daily_cab_rate * req.duration_days) if req.include_local_cab else 0.0

    subtotal = flights_total + hotels_total + cabs_total
    platform_fee = subtotal * 0.03  # 3% SaaS Service Fee
    grand_total = subtotal + platform_fee

    return {
        "status": "Success",
        "breakdown": {
            "flights_total_inr": flights_total,
            "hotels_total_inr": hotels_total,
            "cabs_total_inr": cabs_total,
            "subtotal_inr": subtotal,
            "platform_fee_inr": platform_fee,
            "grand_total_inr": grand_total,
        },
    }


@app.get("/api/v1/history/{user_id}")
async def get_user_history(user_id: str):
    history_records = get_history(user_id)
    return {"status": "Success", "user_id": user_id, "history": history_records}


@app.post("/api/v1/ocr/passport")
async def handle_passport(file: UploadFile = File(...)):
    """Handles real-time OCR extraction from uploaded passport images (JPG, PNG) or PDFs."""
    filename = file.filename.lower()

    if filename.endswith(".pdf"):
        mime_type = "application/pdf"
    elif filename.endswith(".png"):
        mime_type = "image/png"
    elif filename.endswith((".jpg", ".jpeg")):
        mime_type = "image/jpeg"
    else:
        mime_type = file.content_type or "image/jpeg"

    try:
        content = await file.read()
        parsed_data = process_passport_image(content, mime_type=mime_type)

        is_valid = parsed_data.get("is_valid", False) or bool(parsed_data.get("passport_number"))

        return {
            "status": "success" if is_valid else "error",
            "passport_verified": is_valid,
            "passport_details": parsed_data,
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "passport_verified": False}
