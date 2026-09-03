import os
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types


# ==========================================
# Input & Structured Output Schemas
# ==========================================

class GroundTransitInput(BaseModel):
    origin: str
    destination: str
    trip_type: str = "round_trip"  # "one_way" OR "round_trip"
    travel_date: Optional[str] = None


class DynamicTrain(BaseModel):
    train_name: str = Field(description="Name and code of train, e.g. '12429 / Rajdhani Express' or '22436 / Vande Bharat Express'")
    train_number: str = Field(description="5-digit train number")
    class_tier: str = Field(description="Travel class tier, e.g. '3A Tier', '2A Tier', 'CC', 'Sleeper'")
    departure_time: str = Field(description="Departure time in 24-hr format (HH:MM)")
    arrival_time: str = Field(description="Arrival time in 24-hr format (HH:MM)")
    duration: str = Field(description="Trip duration, e.g. '14 hrs 30 mins'")
    one_way_price_inr: float = Field(description="Realistic standard one-way fare in INR")


class DynamicTrainResponse(BaseModel):
    trains: List[DynamicTrain]


class DynamicBus(BaseModel):
    bus_operator: str = Field(description="Realistic intercity bus company, e.g. 'Zingbus Plus', 'IntrCity SmartBus', 'VRL Travels'")
    bus_type: str = Field(description="Type of bus, e.g. 'Volvo Multi-Axle AC Sleeper (2+1)'")
    departure_time: str = Field(description="Departure time (HH:MM)")
    arrival_time: str = Field(description="Arrival time (HH:MM)")
    duration: str = Field(description="Duration of journey, e.g. '15 hrs 45 mins'")
    one_way_price_inr: float = Field(description="Realistic one-way ticket price in INR")


class DynamicBusResponse(BaseModel):
    buses: List[DynamicBus]


class DynamicCabOption(BaseModel):
    service_name: str = Field(description="Cab package name, e.g. 'Private Chauffeur Sedan', 'Full-Day Black Cab Sightseeing'")
    vehicle_type: str = Field(description="Vehicle model/type, e.g. 'Toyota Innova Crysta', 'Sedan (Dzire/Etios)', 'Mercedes E-Class'")
    daily_rate_inr: float = Field(description="Realistic daily rate in INR for this specific city/country")
    inclusions: str = Field(description="Service perks, e.g. 'Airport pickup, 8 hrs / 80 km daily sightseeing, fuel & tolls included'")


class DynamicCabResponse(BaseModel):
    primary_cab: DynamicCabOption
    alternative_options: List[DynamicCabOption]


# ==========================================
# Dynamic Tools Implementation
# ==========================================

def search_trains_tool(payload: GroundTransitInput) -> dict:
    """Dynamically retrieves realistic IRCTC train options using Gemini structured outputs."""
    api_key = os.getenv("GEMINI_API_KEY")
    multiplier = 2 if payload.trip_type == "round_trip" else 1

    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            prompt = (
                f"Find 3 to 4 prominent real-world trains running between '{payload.origin}' and '{payload.destination}'. "
                f"Date: {payload.travel_date or 'Upcoming weekend'}. "
                f"Include popular Indian Railways trains on this sector (Rajdhani, Duronto, Vande Bharat, Superfast Express). "
                f"Provide realistic class tiers (3A, 2A, CC), schedules, travel durations, and accurate IRCTC fare pricing in INR."
            )
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=DynamicTrainResponse,
                ),
            )
            parsed = DynamicTrainResponse.model_validate_json(response.text)

            extracted_trains = []
            for t in parsed.trains:
                extracted_trains.append({
                    "train_name": t.train_name,
                    "train_number": t.train_number,
                    "class_tier": t.class_tier,
                    "departure_time": t.departure_time,
                    "arrival_time": t.arrival_time,
                    "duration": t.duration,
                    "one_way_price_inr": t.one_way_price_inr,
                    "total_price_inr": t.one_way_price_inr * multiplier,
                })
            return {"trains": extracted_trains}
        except Exception as e:
            print(f"Dynamic Train Tool Gemini Error: {e}")

    # Fallback if API key is missing or prompt fails
    return {
        "trains": [
            {
                "train_name": f"Superfast Express ({payload.origin} ➔ {payload.destination})",
                "train_number": "12721",
                "class_tier": "3A Tier",
                "departure_time": "07:30",
                "arrival_time": "21:45",
                "duration": "14 hrs 15 mins",
                "one_way_price_inr": 1850.0,
                "total_price_inr": 1850.0 * multiplier,
            },
            {
                "train_name": f"Rajdhani Express ({payload.origin} ➔ {payload.destination})",
                "train_number": "12437",
                "class_tier": "2A Tier",
                "departure_time": "15:20",
                "arrival_time": "06:10",
                "duration": "14 hrs 50 mins",
                "one_way_price_inr": 2900.0,
                "total_price_inr": 2900.0 * multiplier,
            }
        ]
    }


def search_buses_tool(payload: GroundTransitInput) -> dict:
    """Dynamically retrieves realistic intercity bus operators using Gemini structured outputs."""
    api_key = os.getenv("GEMINI_API_KEY")
    multiplier = 2 if payload.trip_type == "round_trip" else 1

    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            prompt = (
                f"Find 3 to 4 realistic intercity private bus services traveling from '{payload.origin}' to '{payload.destination}'. "
                f"Date: {payload.travel_date or 'Upcoming weekend'}. "
                f"Use actual bus operators common on this corridor (e.g. Zingbus, IntrCity SmartBus, Orange Travels, VRL, SRS). "
                f"Include bus types (AC Sleeper 2+1, Multi-Axle Volvo), departure/arrival times, durations, and realistic seat prices in INR."
            )
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=DynamicBusResponse,
                ),
            )
            parsed = DynamicBusResponse.model_validate_json(response.text)

            extracted_buses = []
            for b in parsed.buses:
                extracted_buses.append({
                    "bus_operator": b.bus_operator,
                    "bus_type": b.bus_type,
                    "departure_time": b.departure_time,
                    "arrival_time": b.arrival_time,
                    "duration": b.duration,
                    "one_way_price_inr": b.one_way_price_inr,
                    "total_price_inr": b.one_way_price_inr * multiplier,
                })
            return {"buses": extracted_buses}
        except Exception as e:
            print(f"Dynamic Bus Tool Gemini Error: {e}")

    # Fallback if API key is missing or prompt fails
    return {
        "buses": [
            {
                "bus_operator": f"Intercity Volvo Sleeper ({payload.origin} ➔ {payload.destination})",
                "bus_type": "Multi-Axle AC Sleeper",
                "departure_time": "19:00",
                "arrival_time": "10:30",
                "duration": "15 hrs 30 mins",
                "one_way_price_inr": 1400.0,
                "total_price_inr": 1400.0 * multiplier,
            }
        ]
    }


def search_local_cabs_tool(destination: str, days: int) -> dict:
    """Dynamically estimates local city cab and private transfer packages using Gemini."""
    api_key = os.getenv("GEMINI_API_KEY")
    duration_days = max(1, days)

    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            prompt = (
                f"Provide realistic tourist cab and chauffeur rates for '{destination}'. "
                f"Trip Duration: {duration_days} days. "
                f"Calculate realistic daily rates in INR converted properly for this city's economy "
                f"(e.g., domestic Indian cities ~₹2,200 to ₹3,500/day; international destinations like London or Dubai ~₹8,000 to ₹15,000/day). "
                f"Include vehicle models and standard package inclusions (airport transfers, daily sightseeing hours/kilometers)."
            )
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=DynamicCabResponse,
                ),
            )
            parsed = DynamicCabResponse.model_validate_json(response.text)
            pri = parsed.primary_cab

            return {
                "cab_service": pri.service_name,
                "vehicle_type": pri.vehicle_type,
                "daily_rate_inr": pri.daily_rate_inr,
                "total_cab_cost_inr": pri.daily_rate_inr * duration_days,
                "inclusions": pri.inclusions,
                "alternatives": [
                    {
                        "service_name": alt.service_name,
                        "vehicle_type": alt.vehicle_type,
                        "daily_rate_inr": alt.daily_rate_inr,
                        "total_cab_cost_inr": alt.daily_rate_inr * duration_days,
                        "inclusions": alt.inclusions,
                    }
                    for alt in parsed.alternative_options
                ]
            }
        except Exception as e:
            print(f"Dynamic Cab Tool Gemini Error: {e}")

    # Default heuristic fallback
    default_rate = 2200.0
    return {
        "cab_service": f"Private Tourist Cab in {destination}",
        "vehicle_type": "Sedan (AC)",
        "daily_rate_inr": default_rate,
        "total_cab_cost_inr": default_rate * duration_days,
        "inclusions": "Airport transfers + 8 hrs/80 km daily sightseeing",
        "alternatives": []
    }

# Aliases to satisfy nodes.py imports
search_trains_tool_dynamic = lambda origin, destination, travel_date, trip_type="round_trip": search_trains_tool(
    GroundTransitInput(origin=origin, destination=destination, travel_date=travel_date, trip_type=trip_type)
)

search_buses_tool_dynamic = lambda origin, destination, travel_date, trip_type="round_trip": search_buses_tool(
    GroundTransitInput(origin=origin, destination=destination, travel_date=travel_date, trip_type=trip_type)
)