import os
import datetime
import json
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.agents.state import AgentState
from app.db.vectordb import vector_db

# --- Dynamic Structured Schemas ---

class QueryExtraction(BaseModel):
    destination: str = Field(description="Clean city destination name")
    origin_airport_code: str = Field(description="3-letter IATA origin airport code")
    destination_airport_code: str = Field(description="3-letter IATA destination airport code")
    duration_days: int = Field(default=3)
    is_international: bool = Field(description="True if origin and destination are in different countries")

class FlightSegment(BaseModel):
    airline: str
    flight_number: str
    from_code: str
    to_code: str
    departure_time: str
    arrival_time: str
    departure_date: str
    arrival_date: str
    layover_after: str = Field(default="", description="Layover transit hub and duration if connecting; empty if direct non-stop")
    day_shift: str = Field(default="", description="e.g. '(Same Day)' or '(+1 Day)'")

class DynamicFlightOption(BaseModel):
    airline: str
    airline_logo: str = Field(default="", description="URL or placeholder for airline logo")
    flight_number: str
    departure_time: str
    arrival_time: str
    total_duration: str
    price_inr: float
    is_direct: bool = Field(description="True if direct non-stop, False if connecting")
    segments: list[FlightSegment]

class DynamicFlightList(BaseModel):
    flights: list[DynamicFlightOption] = Field(description="Exactly 10 diverse, realistic airline flight choices")

class DynamicHotelOption(BaseModel):
    name: str
    price_per_night: float
    rating: float
    image_url: str
    link: str
    amenities: str

class DynamicHotelList(BaseModel):
    hotels: list[DynamicHotelOption] = Field(description="Exactly 12 realistic hotel choices across budget to luxury")

class DynamicTrainOption(BaseModel):
    train_name: str
    train_number: str
    class_tier: str
    departure_time: str
    arrival_time: str
    duration: str
    total_price_inr: float

class DynamicTrainList(BaseModel):
    trains: list[DynamicTrainOption] = Field(description="Minimum 5 realistic train routes")

class DynamicBusOption(BaseModel):
    bus_operator: str
    bus_type: str
    departure_time: str
    arrival_time: str
    duration: str
    total_price_inr: float

class DynamicBusList(BaseModel):
    buses: list[DynamicBusOption] = Field(description="Minimum 5 realistic bus routes")

class CabOption(BaseModel):
    service_name: str
    vehicle_type: str
    daily_rate_inr: float
    inclusions: str

class DynamicCabList(BaseModel):
    cabs: list[CabOption] = Field(description="Exactly 5 distinct options: 1. Sedan, 2. Green EV, 3. SUV, 4. Luxury Chauffeur, 5. Van")

class DynamicCabResponse(BaseModel):
    selected_service: CabOption
    alternative_services: list[CabOption] = Field(description="Exactly 4 distinct alternative services")

class ItineraryResponse(BaseModel):
    draft_itinerary: str
    calculated_cost_inr: float


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


import time

def _call_gemini_structured(client: genai.Client, prompt: str, schema_class):
    """Reliably calls Gemini Flash with fallbacks to ensure zero hardcoded crash."""
    import anthropic
    import json
    
    for model_name in ["gemini-3.5-flash-lite", "gemini-3.1-pro", "gemini-3.8-flash"]:
        for attempt in range(2):
            try:
                res = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=schema_class,
                    ),
                )
                return schema_class.model_validate_json(res.text)
            except Exception as e:
                print(f"Error calling {model_name} (Attempt {attempt+1}): {e}")
                time.sleep(2)
                continue
                
    # Fallback to Claude API
    print("Falling back to Claude API...")
    try:
        claude_key = os.getenv("CLAUDE_API_KEY")
        if claude_key:
            claude = anthropic.Anthropic(api_key=claude_key)
            schema_json = schema_class.model_json_schema()
            msg = claude.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=2048,
                system=f"You are a structured data extractor. You must output ONLY raw, valid JSON matching this schema: {json.dumps(schema_json)}. Do not include markdown blocks or any other text.",
                messages=[{"role": "user", "content": prompt}]
            )
            raw_text = msg.content[0].text.strip()
            # Remove any markdown formatting if present
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1]
                if raw_text.endswith("```"):
                    raw_text = raw_text.rsplit("\n", 1)[0]
                elif raw_text.endswith("```json"):
                    raw_text = raw_text[:-7]
            return schema_class.model_validate_json(raw_text)
    except Exception as e:
        print(f"Claude fallback failed: {e}")
        
    return None


import random

def _generate_dynamic_flights(client: genai.Client, origin: str, dest: str, flight_date: str, direction: str, is_international: bool) -> list:
    spec = (
        f"This is an INTERNATIONAL flight route between {origin} and {dest}. Generate exactly 10 distinct airline options. "
        f"Use a variety of real international carriers (e.g. Emirates, British Airways, Air India, Qatar Airways, Lufthansa, Singapore Airlines, etc.). "
        f"CRITICAL: You MUST include BOTH Direct Non-Stop flights (if they exist) and Connecting flights. "
        f"For connecting flights, the transit hub MUST be dynamically chosen based on the airline (e.g. DXB for Emirates, DOH for Qatar Airways). "
        f"ALL connecting records MUST include realistic connecting flight details (multiple segments)."
        if is_international
        else
        f"This is a DOMESTIC flight route inside India between {origin} and {dest}. Generate exactly 10 distinct flight options. "
        f"Use active Indian domestic carriers (IndiGo, Air India, Akasa Air, Vistara, SpiceJet). "
        f"Provide at least 5-6 DIRECT NON-STOP flights (single segment) and 4-5 connecting flights via DEL/BOM/BLR."
    )
    prompt = (
        f"Generate exactly 10 realistic, completely distinct flight options for route {origin} to {dest} on date {flight_date}.\n"
        f"Direction: {direction}. Is International: {is_international}.\n{spec}\n"
        f"Set realistic total_duration, realistic current market prices in INR, and clean HH:MM departure/arrival times."
    )
    
    parsed = _call_gemini_structured(client, prompt, DynamicFlightList)
    out = []
    
    if not parsed or not parsed.flights:
        # Fallback Mock Data for 429 Quota Exceeded
        airlines = ["Emirates", "British Airways", "Air India", "Qatar Airways", "Lufthansa"] if is_international else ["IndiGo", "Vistara", "Air India", "SpiceJet", "Akasa Air"]
        hubs = ["DXB", "LHR", "DEL", "DOH", "FRA"] if is_international else ["DEL", "BOM", "BLR", "HYD", "MAA"]
        
        flights_data = []
        for i in range(10):
            airline = random.choice(airlines)
            hub = random.choice(hubs)
            is_direct = random.choice([True, False])
            segments = []
            if is_direct:
                segments.append(FlightSegment(airline=airline, flight_number=f"{airline[:2].upper()}{random.randint(100, 999)}", from_code=origin, to_code=dest, departure_time="10:00", arrival_time="14:00", departure_date=flight_date, arrival_date=flight_date, layover_after="", day_shift=""))
            else:
                segments.append(FlightSegment(airline=airline, flight_number=f"{airline[:2].upper()}{random.randint(100, 999)}", from_code=origin, to_code=hub, departure_time="08:00", arrival_time="11:00", departure_date=flight_date, arrival_date=flight_date, layover_after=f"{hub} 2h 30m", day_shift=""))
                segments.append(FlightSegment(airline=airline, flight_number=f"{airline[:2].upper()}{random.randint(100, 999)}", from_code=hub, to_code=dest, departure_time="13:30", arrival_time="18:00", departure_date=flight_date, arrival_date=flight_date, layover_after="", day_shift=""))
                
            flights_data.append(DynamicFlightOption(
                airline=airline,
                airline_logo="",
                flight_number=f"{airline[:2].upper()}{random.randint(100, 999)}",
                departure_time="10:00" if is_direct else "08:00",
                arrival_time="14:00" if is_direct else "18:00",
                total_duration="4h 00m" if is_direct else "10h 00m",
                price_inr=random.randint(25000, 85000) if is_international else random.randint(4000, 15000),
                is_direct=is_direct,
                segments=segments
            ))
        parsed = DynamicFlightList(flights=flights_data)

    for f in parsed.flights:
        fd = f.model_dump()
        fd["direction"] = direction
        fd["trip_direction"] = direction
        fd["flight_date"] = flight_date
        fd["departure_time"] = f"{flight_date} {_sanitize_time(f.departure_time)}"
        fd["arrival_time"] = f"{flight_date} {_sanitize_time(f.arrival_time)}"
        out.append(fd)
    return out


def _generate_dynamic_hotels(client: genai.Client, destination: str, check_in: str, check_out: str) -> list:
    prompt = (
        f"Generate exactly 12 realistic hotel accommodations located in {destination} from {check_in} to {check_out}.\n"
        f"Provide a diverse selection across 3-star budget, 4-star boutique, business executive, and 5-star luxury hotels.\n"
        f"Include realistic per-night prices in INR, review ratings between 3.8 and 4.9, valid amenities, and clean Unsplash hotel image URLs."
    )
    parsed = _call_gemini_structured(client, prompt, DynamicHotelList)
    if not parsed or not parsed.hotels:
        hotel_data = []
        names = ["Grand Hyatt", "Taj Mahal Palace", "ITC Maurya", "The Leela", "Marriott", "Hilton", "Radisson Blu", "Holiday Inn"]
        for i in range(12):
            hotel_data.append(DynamicHotelOption(
                name=f"{random.choice(names)} {destination} {i+1}",
                rating=round(random.uniform(3.8, 4.9), 1),
                price_per_night=float(random.randint(4000, 35000)),
                amenities="Free WiFi, Pool, Spa, Breakfast Included",
                link="https://www.google.com/search?q=hotel",
                image_url="https://images.unsplash.com/photo-1566073771259-6a8506099945?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80"
            ))
        parsed = DynamicHotelList(hotels=hotel_data)
        
    if parsed and parsed.hotels:
        return [h.model_dump() for h in parsed.hotels]
    return []


def _generate_dynamic_transit(client: genai.Client, origin: str, dest: str, travel_date: str) -> tuple[list, list]:
    prompt = (
        f"Generate at least 5 realistic Indian Railways trains (Vande Bharat, Rajdhani, Superfast Express) and "
        f"at least 5 intercity bus operators from {origin} to {dest} on {travel_date}.\n"
        f"Provide realistic schedule times, durations, class tiers, and INR pricing."
    )
    class TransitCombined(BaseModel):
        trains: list[DynamicTrainOption]
        buses: list[DynamicBusOption]

    parsed = _call_gemini_structured(client, prompt, TransitCombined)
    if not parsed:
        trains = []
        buses = []
        for i in range(5):
            trains.append(DynamicTrainOption(
                train_name=f"{random.choice(['Vande Bharat', 'Rajdhani', 'Shatabdi'])} Express",
                train_number=f"{random.randint(11000, 22000)}",
                departure_time="06:00", arrival_time="14:00", duration="8h",
                class_tier="3A", total_price_inr=float(random.randint(1500, 4500))
            ))
            buses.append(DynamicBusOption(
                bus_operator=f"{random.choice(['Volvo', 'Zingbus', 'IntrCity'])} Travels",
                bus_type="AC Sleeper",
                departure_time="21:00", arrival_time="06:00", duration="9h",
                total_price_inr=float(random.randint(800, 2500))
            ))
        parsed = TransitCombined(trains=trains, buses=buses)
        
    if parsed:
        return [t.model_dump() for t in parsed.trains], [b.model_dump() for b in parsed.buses]
    return [], []


def _generate_dynamic_cabs(client: genai.Client, destination: str, days: int, is_international: bool) -> list:
    prompt = (
        f"Generate exactly 5 distinct cab, taxi, and chauffeur rental packages for a traveler visiting {destination} for {days} days.\n"
        f"Is International destination: {is_international}.\n"
        f"Include exactly 5 classes: 1. Standard City Sedan, 2. Eco EV Chauffeur, 3. Premium Family SUV, 4. VIP Luxury Chauffeur, 5. 7-Seater Passenger Van.\n"
        f"Provide authentic service names, vehicle models, realistic daily rates converted to INR, and inclusions."
    )
    parsed = _call_gemini_structured(client, prompt, DynamicCabList)
    out = []
    
    if not parsed or not parsed.cabs:
        cab_data = []
        classes = ["Standard City Sedan", "Eco EV Chauffeur", "Premium Family SUV", "VIP Luxury Chauffeur", "7-Seater Passenger Van"]
        for idx, cname in enumerate(classes):
            cab_data.append(CabOption(
                service_name=cname,
                vehicle_type="Toyota Camry" if idx==0 else "Tesla Model 3" if idx==1 else "Toyota Fortuner" if idx==2 else "Mercedes Benz S-Class" if idx==3 else "Toyota Innova",
                daily_rate_inr=float(random.randint(2500, 15000)),
                inclusions="8 Hours, 80 Kms, Driver Allowance"
            ))
        parsed = DynamicCabList(cabs=cab_data)
        
    if parsed and parsed.cabs:
        for idx, c in enumerate(parsed.cabs):
            cd = c.model_dump()
            cd["total_cab_cost_inr"] = cd["daily_rate_inr"] * days
            cd["is_recommended"] = (idx == 0)
            out.append(cd)
    return out


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

    origin_val = state.get("origin")
    if not origin_val:
        origin_val = "BOM"
    origin = origin_val.strip().upper()
    
    dest_val = state.get("destination")
    if not dest_val:
        dest_val = "LHR"
    destination_name = dest_val.strip()

    duration_days = int(state.get("duration_days") or 3)
    trip_type = state.get("trip_type") or "round_trip"

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

    # 1. Dynamic Route Extraction
    airport_code = destination_name[:3].upper() if destination_name else "LHR"
    is_international = True
    if client:
        prompt = (
            f"Extract origin 3-letter IATA code, destination 3-letter IATA code, and clean destination city name. "
            f"CRITICAL: determine the country of the Origin airport, and the country of the Destination airport. "
            f"Set boolean is_international to True ONLY if the origin and destination are in DIFFERENT countries. "
            f"Origin: '{origin}', Destination: '{destination_name}', User query: '{user_query}'."
        )
        extracted = _call_gemini_structured(client, prompt, QueryExtraction)
        if extracted:
            origin = extracted.origin_airport_code.upper() or origin
            airport_code = extracted.destination_airport_code.upper() or airport_code
            destination_name = extracted.destination or destination_name
            is_international = extracted.is_international

    # OCR Gate
    passport_data = state.get("passport_data") or {}
    passport_verified = state.get("passport_verified", False) or bool(passport_data.get("passport_number"))

    if is_international and not passport_verified:
        return {
            "status": "pending_verification",
            "is_international": True,
            "requires_passport_ocr": True,
            "passport_verified": False,
            "passport_details": {},
            "flight_options": [],
            "hotels_options": [],
            "train_options": [],
            "bus_options": [],
            "cabs_options": [],
            "local_cabs": [],
            "draft_itinerary": "Passport OCR Verification Required.",
            "calculated_cost_inr": 0.0,
            "budget_sufficient": False,
        }

    # 2. Dynamic Flights (5+ Outbound, 5+ Return)
    flights = []
    if client:
        outbound = _generate_dynamic_flights(client, origin, airport_code, from_date, "outbound", is_international)
        returns = _generate_dynamic_flights(client, airport_code, origin, to_date, "return", is_international) if trip_type == "round_trip" else []
        flights = outbound + returns

    # 3. Dynamic Hotels (12 Options)
    hotels = _generate_dynamic_hotels(client, destination_name, from_date, to_date) if client else []

    # 4. Dynamic Transit (Trains & Buses)
    trains, buses = [], []
    if not is_international and client:
        trains, buses = _generate_dynamic_transit(client, origin, destination_name, from_date)

    # 5. Dynamic 5-Cab Option Generation via Gemini
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

    # 6. Exact Lowest Combined Cost Calculation
    cheapest_outbound = min([f["price_inr"] for f in flights if f.get("direction") == "outbound"], default=0.0)
    cheapest_return = min([f["price_inr"] for f in flights if f.get("direction") == "return"], default=0.0)
    flight_cost = cheapest_outbound + (cheapest_return if trip_type == "round_trip" else 0.0)

    cheapest_hotel = min([h["price_per_night"] for h in hotels], default=0.0)
    hotel_cost = cheapest_hotel * nights

    # Calculate cheapest cab from the local_cabs dictionary
    cabs_list = []
    if local_cabs:
        cabs_list.append(local_cabs)
        cabs_list.extend(local_cabs.get("alternatives", []))
    cheapest_cab = min([c.get("total_cab_cost_inr", 0) for c in cabs_list], default=0.0)
    total_calculated_cost = float(flight_cost + hotel_cost + cheapest_cab)

    budget_sufficient = total_budget_inr >= total_calculated_cost

    # 7. Itinerary Generation
    itinerary_text = ""
    if not budget_sufficient:
        itinerary_text = (
            f"## ⚠️ Insufficient Budget Alert\n\n"
            f"- **Estimated Budget Required:** ₹{total_calculated_cost:,.2f}\n"
            f"- **Your Specified Budget:** ₹{total_budget_inr:,.2f}\n"
            f"- **Shortfall:** ₹{(total_calculated_cost - total_budget_inr):,.2f}\n\n"
            f"> Click **Match Budget** above to review and reserve this package."
        )
    elif client:
        itinerary_prompt = (
            f"Create a detailed day-by-day markdown itinerary for a {duration_days}-day trip to {destination_name} ({from_date} to {to_date}).\n"
            f"Calculated package budget: ₹{total_calculated_cost:,.2f}. User preferences: {user_query}."
        )
        it_res = _call_gemini_structured(client, itinerary_prompt, ItineraryResponse)
        if it_res:
            itinerary_text = it_res.draft_itinerary
        else:
            itinerary_text = f"# {duration_days}-Day Trip to {destination_name}\n\nPackage Cost: ₹{total_calculated_cost:,.2f}"

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
        "hotels_options": hotels,
        "train_options": trains,
        "bus_options": buses,
        "cabs_options": [],
        "local_cabs": local_cabs,
        "local_cab": local_cabs,
        "draft_itinerary": itinerary_text,
        "itinerary": itinerary_text,
        "calculated_cost_inr": total_calculated_cost,
        "estimated_cost_inr": total_calculated_cost,
        "budget_sufficient": budget_sufficient,
        "breakdown": {
            "flights": flights,
            "hotels": hotels,
            "trains": trains,
            "buses": buses,
            "cabs": local_cabs,
        },
    }