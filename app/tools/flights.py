from pydantic import BaseModel, Field

class FlightInput(BaseModel):
    origin:str = Field(description="Departure Airport Code, e.g NAG")
    destination: str =Field(description="Arrival Airport Code, e.g BOM")
    date: str= Field(description="Departure date YYYY-MM-DD")

def search_flights_tool(params: FlightInput) -> dict:
    return {
        "flights":[
            {"airline":"Indigo", "flight_no":"6E-204","price_inr":5500,"departure":"08:00"},
            {"airline":"AirIndia", "flight_no":"AI-442","price_inr":9580,"departure":"14:30"}
        ]
    }