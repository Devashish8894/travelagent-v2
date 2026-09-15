import os
import datetime
import json
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

DOMESTIC_AIRPORTS = {
    "NAG", "BOM", "DEL", "BLR", "HYD", "MAA", "CCU", "GOI", "GOX", "PNQ", "COK", "AMD"
}

INTERNATIONAL_MAP = {
    "london": "LHR", "dxb": "DXB", "dubai": "DXB", "singapore": "SIN", 
    "bangkok": "BKK", "paris": "CDG", "new york": "JFK", "lhr": "LHR", 
    "lax": "LAX", "los angeles": "LAX", "ch": "ZRH", "switzerland": "ZRH", "zurich": "ZRH", "geneva": "GVA"
}

# --- Pydantic Schemas for Structured LLM Outputs ---

class QueryExtraction(BaseModel):
    destination: str = Field(description="Clean city name (e.g. Mumbai, London, Los Angeles, Zurich)")
    origin_airport_code: str = Field(description="3-letter IATA origin code")
    destination_airport_code: str = Field(description="3-letter IATA destination code")
    duration_days: int = Field(default=3)
    is_international: bool = Field(description="True ONLY if origin and destination are in different countries")

class FlightSegment(BaseModel):
    airline: str
    flight_number: str
    from_code: str
    to_code: str
    departure_time: str
    arrival_time: str
    departure_date: str
    arrival_date: str
    layover_after: str = Field(default="", description="Layover duration and hub airport if connecting to another leg")
    day_shift: str = Field(default="", description="e.g. '(Same Day)' or '(+1 Day)'")

class DynamicFlightOption(BaseModel):
    airline: str
    airline_logo: str
    flight_number: str
    departure_time: str
    arrival_time: str
    total_duration: str
    price_inr: float
    segments: list[FlightSegment]

class DynamicFlightList(BaseModel):
    flights: list[DynamicFlightOption]

class CabOption(BaseModel):
    service_name: str = Field(description="Name/Type of cab service (e.g., London Black Cab, Private Sightseeing Chauffeur)")
    vehicle_type: str = Field(description="Type of car (e.g., Mercedes E-Class, Toyota Prius, EV SUV, Sedan, 7-Seater Van)")
    daily_rate_inr: float = Field(description="Realistic daily rate in INR for this specific city/country")
    inclusions: str = Field(description="Included perks like Airport transfer, Fuel, Tolls, English-speaking driver")

class DynamicCabResponse(BaseModel):
    selected_service: CabOption
    alternative_services: list[CabOption] = Field(description="Exactly 4 distinct alternative vehicle/service classes")

class ItineraryResponse(BaseModel):
    draft_itinerary: str = Field(description="Markdown itinerary")
    calculated_cost_inr: float = Field(description="Total cost in INR")


def _sanitize_time(time_val: str, default_time: str = "08:00") -> str:
    if not time_val or str(time_val).lower() in ["n/a", "estimated", "none"]:
        return default_time
    val_str = str(time_val).strip()
    if "T" in val_str:
        return val_str.split("T")[1][:5]
    if " " in val_str:
        parts = val_str.split()
        return parts[1][:5] if len(parts) > 1 else parts[0][:5]
    return val_str[:5]


def _generate_dynamic_connecting_flights(client: genai.Client, origin: str, dest: str, flight_date: str, direction: str, is_international: bool) -> list:
    """Uses Gemini to dynamically generate realistic multi-leg or direct flight routes and schedules."""
    prompt = (
        f"Generate 5 realistic airline flight options for route {origin} to {dest} on date {flight_date}. "
        f"Direction: {direction}. Is International: {is_international}. "
        f"If this route typically requires a connection (e.g. BOM to LAX or Europe), provide realistic 2-leg connecting segments with major hub layovers (e.g., AUH, LHR, CDG, DOH, HKG). "
        f"Provide real carrier names (e.g., Etihad, Emirates, Qatar, British Airways, Air India, etc.), approximate flight numbers, realistic total durations (20h+ for transcontinental), and authentic current market prices in INR (single ticket covering both legs). "
        f"Ensure departure times are clean HH:MM."
    )
    try:
        res = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DynamicFlightList,
            ),
        )
        parsed = DynamicFlightList.model_validate_json(res.text)
        out = []
        for f in parsed.flights:
            f_dict = f.model_dump()
            f_dict["direction"] = direction
            f_dict["trip_direction"] = direction
            f_dict["flight_date"] = flight_date
            f_dict["departure_time"] = f"{flight_date} {_sanitize_time(f.departure_time)}"
            f_dict["arrival_time"] = f"{flight_date} {_sanitize_time(f.arrival_time)}"
            out.append(f_dict)
        return out
    except Exception as e:
        print(f"Dynamic Flight Generation Error: {e}")
        # Dynamic heuristic fallback if API call fails
        hub = "AUH" if is_international else origin
        return [{
            "airline": "Etihad Airways" if is_international else "IndiGo",
            "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/EY.png" if is_international else "https://placehold.co/48x48?text=6E",
            "flight_number": "EY 207 / EY 171" if is_international else "6E 101",
            "departure_time": f"{flight_date} 05:00",
            "arrival_time": f"{flight_date} 16:45",
            "total_duration": "22h 15m" if is_international else "2h 15m",
            "price_inr": 92435.0 if is_international else 5500.0,
            "direction": direction,
            "trip_direction": direction,
            "flight_date": flight_date,
            "segments": [
                {
                    "airline": "Etihad Airways" if is_international else "IndiGo",
                    "flight_number": "EY 207" if is_international else "6E 101",
                    "from_code": origin,
                    "to_code": hub if is_international else dest,
                    "departure_time": "05:00",
                    "arrival_time": "06:30" if is_international else "07:15",
                    "departure_date": flight_date,
                    "arrival_date": flight_date,
                    "layover_after": "3h 45m (Transit & Security Clearance)" if is_international else ""
                },
                {
                    "airline": "Etihad Airways",
                    "flight_number": "EY 171",
                    "from_code": hub,
                    "to_code": dest,
                    "departure_time": "10:15",
                    "arrival_time": "16:45",
                    "departure_date": flight_date,
                    "arrival_date": flight_date,
                    "day_shift": "(Same Day)"
                }
            ] if is_international else []
        }]


def retrieve_context_node(state: AgentState) -> dict:
    user_id = state.get("user_id", "default_user")
    query = state.get("user_input", "")
    memories = vector_db.get_user_preferences(user_id=user_id, query=query) if hasattr(vector_db, "get_user_preferences") else []
    knowledge = vector_db.search_knowledge(query=query) if hasattr(vector_db, "search_knowledge") else []
    return {"retrived_memory": memories, "retrived_knowledge": knowledge}


def execution_node(state: AgentState) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key) if api_key else None
    user_query = state.get("user_input", "")
    total_budget_inr = float(state.get("total_budget_inr", 0.0) or state.get("budget_inr", 0.0))

    origin = state.get("origin", "BOM").strip().upper()
    destination_name = state.get("destination", "LAX").strip()
    duration_days = int(state.get("duration_days", 3))
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

    dest_lower = destination_name.lower()
    if dest_lower in INTERNATIONAL_MAP:
        airport_code = INTERNATIONAL_MAP[dest_lower]
        is_international = True
    elif "lax" in dest_lower or "los angeles" in dest_lower:
        airport_code = "LAX"
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
    if client:
        try:
            prompt = f"Determine origin/dest 3-letter IATA airport codes and whether route is international: Origin '{origin}', Destination '{destination_name}', User query: '{user_query}'."
            extraction_res = client.models.generate_content(
                model="gemini-2.5-flash",
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
            "status": "pending_verification",
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
            "breakdown": {
                "flights": [],
                "hotels": [],
                "trains": [],
                "buses": [],
                "local_cabs": {}
            }
        }

    # 4. Fetch Outbound & Return Flights Dynamically
    flights = []
    
    # Try real live search tool first
    raw_outbound = get_real_flights(origin=origin, destination=airport_code, date=from_date, limit=5)
    
    # If it is an intercontinental route or tool returned limited leg data, generate dynamic multi-segment connecting flights
    if is_international and client:
        outbound_flights = _generate_dynamic_connecting_flights(client, origin, airport_code, from_date, "outbound", is_international)
        return_flights = _generate_dynamic_connecting_flights(client, airport_code, origin, to_date, "return", is_international) if trip_type == "round_trip" else []
        flights = outbound_flights + return_flights
    elif raw_outbound:
        for idx, f in enumerate(raw_outbound[:10]):
            dep = _sanitize_time(f.get("departure_time") or f.get("departure"), "06:00")
            arr = _sanitize_time(f.get("arrival_time"), "08:15")
            flights.append({
                "airline": f.get("airline", "IndiGo"),
                "airline_logo": f.get("airline_logo") or "https://placehold.co/48x48?text=Flight",
                "flight_number": f.get("flight_no") or f.get("flight_number") or f"OB-{101 + idx}",
                "departure_time": f"{from_date} {dep}",
                "arrival_time": f"{from_date} {arr}",
                "total_duration": "2h 15m",
                "price_inr": float(f.get("price_inr") or 5500.0),
                "direction": "outbound",
                "trip_direction": "outbound",
                "flight_date": from_date,
                "segments": [
                    {
                        "airline": f.get("airline", "IndiGo"),
                        "flight_number": f.get("flight_no") or f"OB-{101 + idx}",
                        "from_code": origin,
                        "to_code": airport_code,
                        "departure_time": dep,
                        "arrival_time": arr,
                        "departure_date": from_date,
                        "arrival_date": from_date
                    }
                ]
            })

        if trip_type == "round_trip":
            raw_return = get_real_flights(origin=airport_code, destination=origin, date=to_date, limit=10) or raw_outbound
            for idx, f in enumerate(raw_return[:10]):
                dep = _sanitize_time(f.get("departure_time") or f.get("departure"), "17:30")
                arr = _sanitize_time(f.get("arrival_time"), "19:45")
                flights.append({
                    "airline": f.get("airline", "IndiGo"),
                    "airline_logo": f.get("airline_logo") or "https://placehold.co/48x48?text=Flight",
                    "flight_number": f"RT-{f.get('flight_no') or (201 + idx)}",
                    "departure_time": f"{to_date} {dep}",
                    "arrival_time": f"{to_date} {arr}",
                    "total_duration": "2h 15m",
                    "price_inr": float(f.get("price_inr") or 5500.0),
                    "direction": "return",
                    "trip_direction": "return",
                    "flight_date": to_date,
                    "segments": [
                        {
                            "airline": f.get("airline", "IndiGo"),
                            "flight_number": f"RT-{f.get('flight_no') or (201 + idx)}",
                            "from_code": airport_code,
                            "to_code": origin,
                            "departure_time": dep,
                            "arrival_time": arr,
                            "departure_date": to_date,
                            "arrival_date": to_date
                        }
                    ]
                })
    else:
        # Fallback to dynamic tool
        mock_flights = search_flights_tool(FlightInput(origin=origin, destination=airport_code, date=from_date)).get("flights", [])
        for idx, f in enumerate(mock_flights):
            flights.append({
                "airline": f.get("airline", "Airline"),
                "airline_logo": f.get("airline_logo", "https://placehold.co/48x48?text=Flight"),
                "flight_number": f.get("flight_no", f"FL-{idx+1}"),
                "departure_time": f"{from_date} 08:00",
                "arrival_time": f"{from_date} 10:30",
                "total_duration": "2h 30m",
                "price_inr": float(f.get("price_inr") or 6000.0),
                "direction": "outbound",
                "trip_direction": "outbound",
                "flight_date": from_date,
                "segments": []
            })

    # 5. Fetch Hotels (SerpAPI with dynamic fallback)
    raw_hotels = get_real_hotels(location=destination_name, check_in=from_date, check_out=to_date, limit=10)
    hotels = []
    if raw_hotels:
        for h in raw_hotels:
            hotels.append({
                "name": h.get("name"),
                "price_per_night": float(h.get("price_per_night", 12500.0 if is_international else 4500.0)),
                "rating": h.get("rating", 4.3),
                "image_url": h.get("image_url") or "https://images.unsplash.com/photo-1566073771259-6a8506099945?w=500&auto=format&fit=crop&q=60",
                "link": h.get("link", "#"),
            })
    else:
        fallback_hotel_price = 13500.0 if is_international else 4200.0
        mock_hotels = search_hotels_tool(HotelInput(location=destination_name, max_price_inr=25000.0))
        for h in mock_hotels.get("hotels", []):
            hotels.append({
                "name": h.get("name"),
                "price_per_night": float(h.get("price_per_night") or fallback_hotel_price),
                "rating": h.get("rating", 4.2),
                "image_url": "https://images.unsplash.com/photo-1566073771259-6a8506099945?w=500&auto=format&fit=crop&q=60",
                "link": "#",
            })

    # 6. Ground Transit (Domestic Only)
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

    # 7. Dynamic 5-Cab Option Generation via Gemini
    local_cabs = {}
    if client and state.get("include_local_cab", True):
        try:
            cab_prompt = (
                f"Provide 5 realistic, distinct cab/chauffeur options for a tourist visiting '{destination_name}' ({airport_code}). "
                f"Trip Duration: {duration_days} days. Is International: {is_international}. "
                f"Return 1 primary 'selected_service' and exactly 4 distinct 'alternative_services'. "
                f"Include different categories: e.g. Standard Sedan, Family Minivan, Luxury Executive Chauffeur, Green EV, and Budget City Cab. "
                f"Calculate rates converted to INR based on local city norms (e.g. US/Europe chauffeur rates cost significantly more in INR than India)."
            )
            cab_res = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=cab_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=DynamicCabResponse,
                ),
            )
            parsed_cabs = DynamicCabResponse.model_validate_json(cab_res.text)
            primary_cab = parsed_cabs.selected_service
            daily_rate = primary_cab.daily_rate_inr
            
            local_cabs = {
                "cab_service": primary_cab.service_name,
                "vehicle_type": primary_cab.vehicle_type,
                "daily_rate_inr": daily_rate,
                "total_cab_cost_inr": daily_rate * duration_days,
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
            print(f"Dynamic Cab LLM Error: {e}")
            fallback_base = 25000.0 if is_international else 2400.0
            local_cabs = {
                "cab_service": f"Private Sightseeing Chauffeur in {destination_name}",
                "vehicle_type": "Premium Chauffeur SUV" if is_international else "Toyota Dzire Sedan",
                "daily_rate_inr": fallback_base,
                "total_cab_cost_inr": fallback_base * duration_days,
                "inclusions": "Airport pickups, 8 hours daily sightseeing, fuel, tolls & driver",
                "alternatives": [
                    {"service_name": f"Executive VIP Car ({destination_name})", "vehicle_type": "Mercedes E-Class", "daily_rate_inr": fallback_base * 1.3, "total_cab_cost_inr": fallback_base * 1.3 * duration_days, "inclusions": "Airport meet & greet, all city drops"},
                    {"service_name": f"Standard City Sedan ({destination_name})", "vehicle_type": "Camry / Sedan", "daily_rate_inr": fallback_base * 0.8, "total_cab_cost_inr": fallback_base * 0.8 * duration_days, "inclusions": "Airport pickup + 6 hours sightseeing"},
                    {"service_name": f"Eco EV Chauffeur ({destination_name})", "vehicle_type": "Tesla Model Y / Ioniq", "daily_rate_inr": fallback_base * 0.9, "total_cab_cost_inr": fallback_base * 0.9 * duration_days, "inclusions": "Zero-emission city sightseeing"},
                    {"service_name": f"Group Touring Van ({destination_name})", "vehicle_type": "7-Seater Passenger Van", "daily_rate_inr": fallback_base * 1.4, "total_cab_cost_inr": fallback_base * 1.4 * duration_days, "inclusions": "Spacious luggage van + full-day driver"}
                ]
            }

    # 8. Lowest Price Calculation per tab
    cheapest_outbound = min([f["price_inr"] for f in flights if f.get("direction") == "outbound"], default=0.0)
    cheapest_return = min([f["price_inr"] for f in flights if f.get("direction") == "return"], default=0.0)
    flight_cost = cheapest_outbound + (cheapest_return if trip_type == "round_trip" else 0.0)

    cheapest_hotel = min([h["price_per_night"] for h in hotels], default=0.0)
    hotel_cost = cheapest_hotel * nights
    cab_cost = local_cabs.get("total_cab_cost_inr", 0.0) if state.get("include_local_cab", True) else 0.0
    total_calculated_cost = float(flight_cost + hotel_cost + cab_cost)

    budget_sufficient = total_budget_inr >= total_calculated_cost

    # 9. Dynamic Markdown Itinerary
    if not budget_sufficient:
        itinerary_text = (
            f"## ⚠️ Insufficient Budget Alert\n\n"
            f"- **Estimated Budget Required:** ₹{total_calculated_cost:,.2f}\n"
            f"- **Your Specified Budget:** ₹{total_budget_inr:,.2f}\n"
            f"- **Shortfall:** ₹{(total_calculated_cost - total_budget_inr):,.2f}\n\n"
            f"> Please click **Update Budget** above to view and unlock booking options for this package."
        )
    else:
        itinerary_text = (
            f"# {duration_days}-Day Trip to {destination_name}\n\n"
            f"- **Dates:** {from_date} to {to_date}\n"
            f"- **Outbound Connecting Flight:** ₹{cheapest_outbound:,.2f} (Single ticket including transit)\n"
            f"- **Return Connecting Flight:** ₹{cheapest_return:,.2f} (Single ticket including transit)\n"
            f"- **Hotel ({nights} Nights):** ₹{hotel_cost:,.2f}\n"
            f"- **Chauffeur Sightseeing:** ₹{cab_cost:,.2f}\n\n"
            f"Your budget of ₹{total_budget_inr:,.2f} covers this estimated trip cost of ₹{total_calculated_cost:,.2f}."
        )
        if client:
            try:
                prompt = (
                    f"Create a detailed day-by-day itinerary for {duration_days} days in {destination_name}. "
                    f"Dates: {from_date} to {to_date}. Budget INR: {total_calculated_cost}. User preferences: {user_query}"
                )
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
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
        "status": "Success",
        "user_id": state.get("user_id", "usr_dev_01"),
        "origin": origin,
        "destination": destination_name,
        "from_date": from_date,
        "to_date": to_date,
        "duration_days": duration_days,
        "prompt": user_query,
        "is_international": is_international,
        "requires_passport_ocr": False,
        "passport_verified": passport_verified,
        "passport_details": passport_data,
        "flight_options": flights,
        "train_options": trains.get("trains", []),
        "bus_options": buses.get("buses", []),
        "local_cab": local_cabs,
        "hotels_options": hotels,
        "draft_itinerary": itinerary_text,
        "itinerary": itinerary_text,
        "calculated_cost_inr": total_calculated_cost,
        "estimated_cost_inr": total_calculated_cost,
        "budget_sufficient": budget_sufficient,
        "breakdown": {
            "flights": flights,
            "hotels": hotels,
            "trains": trains.get("trains", []),
            "buses": buses.get("buses", []),
            "local_cabs": local_cabs,
        }
    }