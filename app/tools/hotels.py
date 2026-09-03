from pydantic import BaseModel,Field

class HotelInput(BaseModel):
    location: str=Field(description="Destination City name")
    max_price_inr: float=Field(description="Max price per night in Inr")

def search_hotels_tool(params: HotelInput) -> dict:
    return {
        "hotels":[
            {"name":f"Grand {params.location} Hotel", "price_per_night": min(params.max_price_inr,6000), "rating": 4.5},
            {"name":f"Center Stay {params.location} Hotel", "price_per_night": min(params.max_price_inr * 0.7, 4000), "rating": 4.2}
        ]
    }