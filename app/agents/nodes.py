import os
import datetime
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.agents.state import AgentState
from app.db.vectordb import vector_db
from app.tools.serp_tools import get_real_flights, get_real_hotels
from app.tools.transit import (
    GroundTransitInput,
    search_buses_tool,
    search_local_cabs_tool,
    search_trains_tool,
)
from app.tools.flights import search_flights_tool, FlightInput
from app.tools.hotels import search_hotels_tool, HotelInput
from app.tools.transit import (
    GroundTransitInput,
    search_buses_tool,
    search_local_cabs_tool,
    search_trains_tool,
)

DOMESTIC_AIRPORTS = {
    "NAG", "BOM", "DEL", "BLR", "HYD", "MAA", "CCU", "GOI", "GOX", "PNQ", "COK", "AMD"
}

INTERNATIONAL_MAP = {
    "london": "LHR", "dxb": "DXB", "dubai": "DXB", "singapore": "SIN", 
    "bangkok": "BKK", "paris": "CDG", "new york": "JFK", "lhr": "LHR"
}

class QueryExtraction(BaseModel):
    destination: str = Field(description="Clean city name (e.g. Mumbai, London)")
    origin_airport_code: str = Field(description="3-letter IATA origin code")
    destination_airport_code: str = Field(description="3-letter IATA destination code")
    duration_days: int = Field(default=3)
    is_international: bool = Field(description="True ONLY if origin and destination are in different countries")

class ItineraryResponse(BaseModel):
    draft_itinerary: str = Field(description="Markdown itinerary")
    calculated_cost_inr: float = Field(description="Total cost in INR")

class CabOption(BaseModel):
    service_name: str = Field(description="Name/Type of cab service (e.g., London Black Cab, Private Airport Chauffeur, Sedan Sightseeing)")
    vehicle_type: str = Field(description="Type of car (e.g., Mercedes E-Class, Toyota Prius, EV SUV, Sedan)")
    daily_rate_inr: float = Field(description="Realistic daily rate in INR for this specific city/country")
    inclusions: str = Field(description="Included perks like Airport transfer, Fuel, Tolls, English-speaking driver")

class DynamicCabResponse(BaseModel):
    selected_service: CabOption
    alternative_services: list[CabOption]

def retrieve_context_node(state: AgentState) -> dict:
    user_id = state.get("user_id", "default_user")
    query = state.get("user_input", "")
    memories = vector_db.get_user_preferences(user_id=user_id, query=query) if hasattr(vector_db, "get_user_preferences") else []
    knowledge = vector_db.search_knowledge(query=query) if hasattr(vector_db, "search_knowledge") else []
    return {"retrived_memory": memories, "retrived_knowledge": knowledge}

def execution_node(state: AgentState) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    user_query = state.get("user_input", "")
    total_budget_inr = float(state.get("total_budget_inr", 0.0))

    origin = state.get("origin", "NAG").strip().upper()
    destination_name = state.get("destination", "BOM").strip()
    duration_days = state.get("duration_days", 3)
    trip_type = state.get("trip_type", "round_trip")
    
    # 1. Date Calculations
    from_date = state.get("from_date")
    to_date = state.get("to_date")
    today = datetime.date.today()

    if not from_date:
        from_date = (today + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    if not to_date:
        start_dt = datetime.datetime.strptime(from_date, "%Y-%m-%d").date()
        to_date = (start_dt + datetime.timedelta(days=duration_days)).strftime("%Y-%m-%d")
    else:
        try:
            d1 = datetime.datetime.strptime(from_date, "%Y-%m-%d").date()
            d2 = datetime.datetime.strptime(to_date, "%Y-%m-%d").date()
            diff = (d2 - d1).days
            if diff > 0:
                duration_days = diff
        except Exception:
            pass

    nights = max(1, duration_days - 1)

    # Fast Airport Code Mapping
    dest_lower = destination_name.lower()
    if dest_lower in INTERNATIONAL_MAP:
        airport_code = INTERNATIONAL_MAP[dest_lower]
        is_international = True
    elif "bom" in dest_lower or "mumbai" in dest_lower:
        airport_code = "BOM"
        is_international = False
    elif "goa" in dest_lower or "goi" in dest_lower:
        airport_code = "GOI"
        is_international = False
    else:
        airport_code = "DEL"
        is_international = False

    passport_data = state.get("passport_data") or {}
    passport_verified = state.get("passport_verified", False) or bool(passport_data.get("passport_number"))

    # 2. Dynamic Route Verification with Gemini
    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            prompt = f"Determine origin/dest 3-letter IATA airport codes and whether route is international: Origin '{origin}', Destination '{destination_name}', User query: '{user_query}'."
            extraction_res = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=QueryExtraction,
                ),
            )
            extracted = QueryExtraction.model_validate_json(extraction_res.text)
            origin = extracted.origin_airport_code.upper() or origin
            airport_code = extracted.destination_airport_code.upper() or airport_code
            destination_name = extracted.destination or destination_name
            is_international = extracted.is_international
        except Exception:
            if origin in DOMESTIC_AIRPORTS and airport_code in DOMESTIC_AIRPORTS:
                is_international = False
            else:
                is_international = (origin not in DOMESTIC_AIRPORTS) or (airport_code not in DOMESTIC_AIRPORTS)

    # 3. OCR GATE: Block international routes until verified
    if is_international and not passport_verified:
        return {
            "is_international": True,
            "requires_passport_ocr": True,
            "passport_verified": False,
            "passport_details": {},
            "flight_options": [],
            "train_options": [],
            "bus_options": [],
            "local_cab": {},
            "hotels_options": [],
            "draft_itinerary": "Passport OCR Verification Required.",
            "calculated_cost_inr": 0.0,
            "budget_sufficient": False,
        }

    # 4. Fetch Flights (SerpAPI with fallback)
    raw_flights = get_real_flights(origin=origin, destination=airport_code, date=from_date, return_date=to_date if trip_type == "round_trip" else None, limit=10)
    flights = []
    if raw_flights:
        for f in raw_flights:
            flights.append({
                "airline": f.get("airline", "Airline"),
                "airline_logo": f.get("airline_logo") or "https://placehold.co/48x48?text=Flight",
                "flight_number": f.get("flight_no", "N/A"),
                "departure_time": f.get("departure_time", "N/A"),
                "arrival_time": f.get("arrival_time", "N/A"),
                "price_inr": f.get("price_inr", 0.0),
            })
    else:
        mock_res = search_flights_tool(FlightInput(origin=origin, destination=airport_code, date=from_date))
        for f in mock_res.get("flights", []):
            flights.append({
                "airline": f.get("airline"),
                "airline_logo": f.get("airline_logo", "https://placehold.co/48x48?text=Flight"),
                "flight_number": f.get("flight_no"),
                "departure_time": f.get("departure"),
                "arrival_time": "Estimated",
                "price_inr": f.get("price_inr"),
            })

    # 5. Fetch Hotels (SerpAPI with fallback)
    raw_hotels = get_real_hotels(location=destination_name, check_in=from_date, check_out=to_date, limit=10)
    hotels = []
    if raw_hotels:
        for h in raw_hotels:
            hotels.append({
                "name": h.get("name"),
                "price_per_night": h.get("price_per_night", 3500.0),
                "rating": h.get("rating", 4.2),
                "image_url": h.get("image_url") or "https://images.unsplash.com/photo-1566073771259-6a8506099945?w=500&auto=format&fit=crop&q=60",
                "link": h.get("link", "#"),
            })
    else:
        mock_hotels = search_hotels_tool(HotelInput(location=destination_name, max_price_inr=5000.0))
        for h in mock_hotels.get("hotels", []):
            hotels.append({
                "name": h.get("name"),
                "price_per_night": h.get("price_per_night"),
                "rating": h.get("rating"),
                "image_url": "https://images.unsplash.com/photo-1566073771259-6a8506099945?w=500&auto=format&fit=crop&q=60",
                "link": "#",
            })

    #5.5 Trains and Bus details via Gemini
    # 6. Ground Transit (Dynamic fetching for domestic routes)
    trains, buses = {"trains": []}, {"buses": []}
    if not is_international:
        transit_payload = GroundTransitInput(
            origin=origin,
            destination=destination_name,
            trip_type=trip_type,
            travel_date=from_date
        )
        trains = search_trains_tool(transit_payload)
        buses = search_buses_tool(transit_payload)

    # Dynamic Cab Estimation via Gemini
    local_cabs = {}
    if api_key and state.get("include_local_cab", True):
        try:
            client = genai.Client(api_key=api_key)
            cab_prompt = (
                f"Provide realistic daily private cab and chauffeur options for a tourist in '{destination_name}' ({airport_code}). "
                f"Trip Duration: {duration_days} days. Is International: {is_international}. "
                f"Calculate rates converted to INR based on local city norms (e.g., London cabs cost more in INR than India). "
                f"Ensure realistic pricing for full-day sightseeing and airport transfers."
            )
            cab_res = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=cab_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=DynamicCabResponse,
                ),
            )
            parsed_cabs = DynamicCabResponse.model_validate_json(cab_res.text)
            primary_cab = parsed_cabs.selected_service
            
            daily_rate = primary_cab.daily_rate_inr
            total_cab_cost = daily_rate * duration_days
            
            local_cabs = {
                "cab_service": primary_cab.service_name,
                "vehicle_type": primary_cab.vehicle_type,
                "daily_rate_inr": daily_rate,
                "total_cab_cost_inr": total_cab_cost,
                "inclusions": primary_cab.inclusions,
                "alternatives": [
                    {
                        "service_name": alt.service_name,
                        "vehicle_type": alt.vehicle_type,
                        "daily_rate_inr": alt.daily_rate_inr,
                        "total_cab_cost_inr": alt.daily_rate_inr * duration_days,
                        "inclusions": alt.inclusions,
                    }
                    for alt in parsed_cabs.alternative_services
                ]
            }
        except Exception as e:
            print(f"Dynamic Cab Gemini Error: {e}")
            fallback_rate = 8500.0 if is_international else 2200.0
            local_cabs = {
                "cab_service": f"Private Tourist Cab in {destination_name}",
                "vehicle_type": "Premium Sedan",
                "daily_rate_inr": fallback_rate,
                "total_cab_cost_inr": fallback_rate * duration_days,
                "inclusions": "Airport pickup, 8 hours/80 km daily sightseeing",
                "alternatives": []
            }
    else:
        fallback_rate = 8500.0 if is_international else 2200.0
        local_cabs = {
            "cab_service": f"Private Sedan in {destination_name}",
            "vehicle_type": "Standard Sedan",
            "daily_rate_inr": fallback_rate,
            "total_cab_cost_inr": fallback_rate * duration_days,
            "inclusions": "Airport transfers + daily sightseeing",
            "alternatives": []
        }

    # 7. Total Calculation & Budget Check
    flight_cost = (flights[0]["price_inr"] * (2 if trip_type == "round_trip" else 1)) if flights else 0.0
    hotel_cost = (hotels[0]["price_per_night"] * nights) if hotels else 0.0
    cab_cost = local_cabs.get("total_cab_cost_inr", 0.0) if state.get("include_local_cab", True) else 0.0
    total_calculated_cost = float(flight_cost + hotel_cost + cab_cost)

    budget_sufficient = total_budget_inr >= total_calculated_cost

    # 8. Itinerary Logic with Budget Guardrail
    if not budget_sufficient:
        itinerary_text = (
            f"## ⚠️ Insufficient Budget Alert\n\n"
            f"- **Estimated Budget Required:** ₹{total_calculated_cost:,.2f}\n"
            f"- **Your Specified Budget:** ₹{total_budget_inr:,.2f}\n"
            f"- **Shortfall:** ₹{(total_calculated_cost - total_budget_inr):,.2f}\n\n"
            f"> Please increase your budget by at least **₹{(total_calculated_cost - total_budget_inr):,.2f}** to view and book flight/hotel options for this trip."
        )
    else:
        itinerary_text = (
            f"# {duration_days}-Day Trip to {destination_name}\n\n"
            f"- **Dates:** {from_date} to {to_date}\n"
            f"- **Flight Cost:** ₹{flight_cost:,.2f}\n"
            f"- **Hotel ({nights} Nights):** ₹{hotel_cost:,.2f}\n"
            f"- **Sightseeing Cab:** ₹{cab_cost:,.2f}\n\n"
            f"Your budget of ₹{total_budget_inr:,.2f} comfortably covers this estimated trip cost of ₹{total_calculated_cost:,.2f}."
        )
        if api_key:
            try:
                prompt = (
                    f"Create a detailed day-by-day itinerary for {duration_days} days in {destination_name}. "
                    f"Dates: {from_date} to {to_date}. Budget INR: {total_calculated_cost}. User preferences: {user_query}"
                )
                response = client.models.generate_content(
                    model="gemini-3.5-flash-lite",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ItineraryResponse,
                    ),
                )
                parsed = ItineraryResponse.model_validate_json(response.text)
                itinerary_text = parsed.draft_itinerary
            except Exception:
                pass

    return {
        "is_international": is_international,
        "requires_passport_ocr": False,
        "passport_verified": passport_verified,
        "passport_details": passport_data,
        "flight_options": flights if budget_sufficient else [],
        "train_options": trains.get("trains", []) if budget_sufficient else [],
        "bus_options": buses.get("buses", []) if budget_sufficient else [],
        "local_cab": local_cabs if budget_sufficient else {},
        "hotels_options": hotels if budget_sufficient else [],
        "draft_itinerary": itinerary_text,
        "calculated_cost_inr": total_calculated_cost,
        "budget_sufficient": budget_sufficient,
    }