import os
from google import genai
from google.genai import types
from pydantic import BaseModel, Field


class PassportData(BaseModel):
    full_name: str = Field(default="", description="Full legal name of the passport holder")
    passport_number: str = Field(default="", description="Passport / Document number")
    expiry_date: str = Field(default="", description="Expiration date in YYYY-MM-DD format")
    nationality: str = Field(default="", description="Country of nationality")
    date_of_birth: str = Field(default="", description="Date of birth in YYYY-MM-DD format")
    is_valid: bool = Field(default=False, description="True if a valid passport document is identified")


def process_passport_image(file_source: str | bytes, mime_type: str = "image/jpeg") -> dict:
    """Extracts passport details dynamically from Image or PDF (filepath or bytes) using Gemini 2.5 Flash."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"status": "error", "message": "GEMINI_API_KEY environment variable missing."}

    client = genai.Client(api_key=api_key)

    # Read bytes if string filepath is provided
    if isinstance(file_source, str):
        if not os.path.exists(file_source):
            return {"status": "error", "message": f"File path {file_source} does not exist."}
        with open(file_source, "rb") as f:
            file_bytes = f.read()
    else:
        file_bytes = file_source

    prompt = (
        "Analyze this passport document (image or PDF page). "
        "Extract legal full name, passport number, expiry date, nationality, and date of birth. "
        "If legible and valid, set is_valid to true."
    )

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PassportData,
            ),
        )

        extracted = PassportData.model_validate_json(response.text)
        result_dict = extracted.model_dump()
        result_dict["is_valid"] = bool(extracted.passport_number or extracted.full_name)

        return result_dict

    except Exception as e:
        return {"is_valid": False, "error": str(e)}