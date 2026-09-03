import os
from serpapi import GoogleSearch

def get_real_flights(origin: str, destination: str, date: str, return_date: str = None, limit: int = 10):
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        return []

    params = {
        "engine": "google_flights",
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": date,
        "currency": "INR",
        "hl": "en",
        "gl": "in",
        "api_key": api_key,
    }
    if return_date:
        params["return_date"] = return_date

    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        flight_results = results.get("best_flights", []) + results.get("other_flights", [])

        extracted = []
        for item in flight_results[:limit]:
            flight_info = item.get("flights", [{}])[0]
            extracted.append({
                "airline": flight_info.get("airline", "Airline"),
                "airline_logo": flight_info.get("airline_logo") or "https://placehold.co/48x48?text=Flight",
                "flight_no": flight_info.get("flight_number", "N/A"),
                "departure_time": flight_info.get("departure_airport", {}).get("time", "N/A"),
                "arrival_time": flight_info.get("arrival_airport", {}).get("time", "N/A"),
                "price_inr": item.get("price", 0.0),
                "duration_min": item.get("total_duration", "N/A"),
            })
        return extracted
    except Exception as e:
        print(f"SerpApi Flight Error: {e}")
        return []


def get_real_hotels(location: str, check_in: str, check_out: str, limit: int = 10):
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        return []

    params = {
        "engine": "google_hotels",
        "q": f"Hotels in {location}",
        "check_in_date": check_in,
        "check_out_date": check_out,
        "currency": "INR",
        "gl": "in",
        "hl": "en",
        "api_key": api_key,
    }

    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        properties = results.get("properties", [])

        extracted = []
        for p in properties[:limit]:
            rate = p.get("rate_per_night", {})
            
            # Extract thumbnail / property image from SerpApi response
            images_list = p.get("images", [])
            image_url = ""
            if images_list and isinstance(images_list, list):
                first_img = images_list[0]
                image_url = first_img.get("thumbnail") or first_img.get("original_image") if isinstance(first_img, dict) else str(first_img)
            
            if not image_url:
                image_url = p.get("thumbnail") or "https://images.unsplash.com/photo-1566073771259-6a8506099945?w=500&auto=format&fit=crop&q=60"

            extracted.append({
                "name": p.get("name", "Hotel"),
                "rating": p.get("overall_rating", 4.0),
                "reviews_count": p.get("reviews", 0),
                "price_per_night": rate.get("extracted_before_taxes_fees") or rate.get("extracted_lowest") or 3500.0,
                "image_url": image_url,
                "link": p.get("link", "#"),
            })
        return extracted
    except Exception as e:
        print(f"SerpApi Hotel Error: {e}")
        return []