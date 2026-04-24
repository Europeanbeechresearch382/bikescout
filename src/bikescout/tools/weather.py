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
    Fetches a full 24-hour hourly forecast from Open-Meteo.

    Args:
        lat: Latitude of the target location.
        lon: Longitude of the target location.
        target_date: Optional 'YYYY-MM-DD' string. Defaults to today.
    """
    url = "https://api.open-meteo.com/v1/forecast"

    # 1. Date Handling: Default to current date if no target_date is provided
    if target_date is None:
        target_date = date.today().isoformat()

    # 2. API Parameters:
    # Requesting full 24h data by pinning start/end dates to the target_date.
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

        # 3. Dynamic Reference Index:
        # For today's analysis, we use the current real-time hour.
        # For future/past dates, we use 08:00 AM as the standard pro-cycling baseline.
        is_today = target_date == date.today().isoformat()
        current_hour_now = datetime.now().hour
        ref_idx = current_hour_now if is_today else 8

        # 4. Full-Day Tactical Forecast:
        # We iterate through all 24 hours (0-23) to avoid truncating the race window.
        # This allows ProCyclingEngine to slice any interval (e.g., 10:00 to 16:00).
        forecast_summary = []
        for i in range(24):
            forecast_summary.append({
                "time": hourly["time"][i].split("T")[1], # Returns "HH:MM"
                "temp": f"{hourly['temperature_2m'][i]}°C",
                "rain_prob": f"{hourly['precipitation_probability'][i]}%",
                "wind": f"{hourly['windspeed_10m'][i]} km/h"
            })

        # 5. Extract Baseline Reference Conditions:
        # These values drive the default safety advice and nutrition baselines.
        curr_temp = hourly['temperature_2m'][ref_idx]
        curr_rain = hourly['precipitation_probability'][ref_idx]
        curr_wind = hourly['windspeed_10m'][ref_idx]

        # 6. Return Structured Multi-Temporal Payload
        return {
            "status": "Success",
            "metadata": {
                "date_analyzed": target_date,
                "is_future_planning": not is_today,
                "location": {"lat": lat, "lon": lon},
                "data_points": len(forecast_summary)
            },
            "tactical_forecast": forecast_summary, # Contains the full 24h set
            "reference_conditions": {
                "temp": curr_temp,
                "rain_prob": curr_rain,
                "wind_speed": curr_wind,
                "reference_hour": f"{ref_idx}:00"
            },
            # Adaptive advice based on the reference point
            "safety_advice": get_safety_advice(curr_temp, curr_rain, curr_wind)
        }

    except requests.exceptions.RequestException as e:
        return {"status": "Error", "message": f"Weather API Connection Error: {str(e)}"}
    except Exception as e:
        return {"status": "Error", "message": f"Unexpected Weather Engine Error: {str(e)}"}