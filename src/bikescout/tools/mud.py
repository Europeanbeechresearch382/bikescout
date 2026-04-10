import requests
from datetime import datetime, timedelta

OPEN_METEO_ARCHIVE_URL = 'https://archive-api.open-meteo.com/v1/archive'

def get_mud_risk_analysis(lat, lon, surface_type):
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=3)

    # Open-Meteo Archive API (No Key Required for basic use)
    url = OPEN_METEO_ARCHIVE_URL
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": "precipitation_sum", "timezone": "auto"
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        total_rain = sum(data.get('daily', {}).get('precipitation_sum', []))

        # Sensitivity Logic
        soil_sensitivity = {"clay": 1.0, "dirt": 0.8, "earth": 0.8, "grass": 0.6, "gravel": 0.3, "sand": 0.1, "asphalt": 0.0}
        sensitivity = soil_sensitivity.get(surface_type.lower(), 0.7)

        mud_index = total_rain * sensitivity

        if mud_index < 5: risk, advice = "Low", "Dry or ideal grip."
        elif mud_index < 15: risk, advice = "Medium", "Damp soil, slippery roots possible."
        else: risk, advice = "High", "Heavy mud. Potential drivetrain damage."

        return {
            "status": "Success",
            "rain_last_72h": f"{total_rain}mm",
            "mud_risk_score": risk,
            "safety_advice": advice
        }
    except:
        return {"status": "Error", "mud_risk_score": "Unknown"}