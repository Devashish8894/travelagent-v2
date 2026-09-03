from typing import TypedDict, List, Dict, Any, Optional

class AgentState(TypedDict):
    user_id: str
    user_input: str
    total_budget_inr: float
    origin: str
    destination: str
    destination_airport_code: Optional[str]  # Added
    duration_days: int
    trip_type: str
    is_international: bool
    requires_passport_ocr: bool              # Renamed from req_passport_ocr for consistency
    preferred_transit: List[str]
    include_local_cab: bool
    include_hotel: bool
    selected_flight_index: Optional[int]
    selected_hotel_index: Optional[int]
    passport_verified: Optional[bool]        # Added
    passport_data: Optional[Dict[str, Any]]   # Added
    retrived_memory: List[Any]
    retrived_knowledge: List[Any]
    flight_options: List[Any]
    train_options: List[Any]
    bus_options: List[Any]
    local_cab: Dict[str, Any]
    hotels_options: List[Any]
    calculated_cost_inr: float
    draft_itinerary: str