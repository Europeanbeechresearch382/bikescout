import requests
from datetime import datetime, date

OPEN_METEO_URL = 'https://api.open-meteo.com/v1/forecast'

def get_safety_advice(temp: float, rain_prob: int, wind_speed: float) -> str:
    """
    Evaluates cycling safety based on multi-factor weather thresholds.
    """
    # 1. Critical Danger (Severe weather)
    if rain_prob > 50 or wind_speed > 45:
        return "❌ NOT RECOMMENDED: High risk of heavy rain or dangerous wind gusts."

    # 2. Significant Hazards
    if rain_prob > 25:
        return "⚠️ CAUTION: High rain probability. Bring a waterproof jacket."

    if wind_speed > 25:
        return "💨 WINDY: Strong winds. Use caution on descents and open ridges."

    # 3. Temperature/Gear Advice
    if temp < 7:
        return "❄️ COLD: Near freezing. Wear thermal layers and winter gloves."

    if temp > 30:
        return "☀️ HOT: Heat exhaustion risk. Bring extra water and electrolytes."

    if temp < 15:
        return "🌥️ CHILLY: Light jacket or arm warmers recommended."

    # 4. Optimal Conditions
    return "✅ IDEAL: Perfect conditions for a great ride!"

def get_weather_forecast(lat: float, lon: float, target_date: str = None):
    """
    Advanced cycling-specific weather engine for BikeScout.
    Fetches hourly forecast data from Open-Meteo.

    Args:
        lat: Latitude of the target location.
        lon: Longitude of the target location.
        target_date: Optional string in 'YYYY-MM-DD' format.
                     If provided, retrieves forecast for that specific day.
                     If None, defaults to today's real-time forecast.
    """
    url = "https://api.open-meteo.com/v1/forecast"

    # 1. Date Handling: Default to current date if no target_date is provided
    if target_date is None:
        target_date = date.today().isoformat()

    # 2. API Parameters:
    # We use start_date and end_date to pin the analysis to a specific event day.
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ["temperature_2m", "precipitation_probability", "windspeed_10m", "weathercode"],
        "timezone": "auto",
        "start_date": target_date,
        "end_date": target_date
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "hourly" not in data:
            return {"status": "Error", "message": "No hourly data returned from weather provider."}

        hourly = data["hourly"]

        # 3. Reference Hour Logic:
        # If the analyzed day is TODAY, we start from the current hour.
        # If it's a FUTURE date (e.g., a race), we start at 08:00 AM for tactical planning.
        is_today = target_date == date.today().isoformat()
        current_hour_now = datetime.now().hour
        start_hour = current_hour_now if is_today else 8

        # 4. Extracting Reference Conditions:
        # These are used to generate the Safety Advice (gear, tire pressure, etc.)
        curr_temp = hourly['temperature_2m'][start_hour]
        curr_rain = hourly['precipitation_probability'][start_hour]
        curr_wind = hourly['windspeed_10m'][start_hour]

        # 5. Build Forecast Window:
        # We capture an 8-hour block to cover the full duration of most cycling stages.
        forecast_summary = []
        for i in range(start_hour, min(start_hour + 8, 24)):
            forecast_summary.append({
                "time": hourly["time"][i].split("T")[1], # Extract HH:MM
                "temp": f"{hourly['temperature_2m'][i]}°C",
                "rain_prob": f"{hourly['precipitation_probability'][i]}%",
                "wind": f"{hourly['windspeed_10m'][i]} km/h"
            })

        # 6. Return Structured Payload
        return {
            "status": "Success",
            "metadata": {
                "date_analyzed": target_date,
                "is_future_planning": not is_today,
                "location": {"lat": lat, "lon": lon}
            },
            "tactical_forecast": forecast_summary,
            "reference_conditions": {
                "temp": curr_temp,
                "rain_prob": curr_rain,
                "wind_speed": curr_wind,
                "reference_hour": f"{start_hour}:00"
            },
            # This method should be your existing logic for gear/risk advice
            "safety_advice": get_safety_advice(curr_temp, curr_rain, curr_wind)
        }

    except requests.exceptions.RequestException as e:
        return {"status": "Error", "message": f"Weather API Connection Error: {str(e)}"}
    except Exception as e:
        return {"status": "Error", "message": f"Unexpected Weather Engine Error: {str(e)}"}