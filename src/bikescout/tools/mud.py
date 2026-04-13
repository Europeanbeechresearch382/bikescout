from datetime import datetime, timedelta
import requests


OPEN_METEO_ARCHIVE_URL = 'https://archive-api.open-meteo.com/v1/archive'


def get_mud_risk_analysis(lat, lon, surface_type):
    """
    Tactical Mud Risk Analysis v2: Heuristic Environmental Model.
    Accounts for cumulative rainfall vs. atmospheric drying efficiency.
    """
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=3)

    # Open-Meteo Archive API - Fetching Rain, Temp and Wind for Drying Factor
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": ["precipitation_sum", "temperature_2m_max", "wind_speed_10m_max"],
        "timezone": "auto"
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json().get('daily', {})

        # 1. Environmental Data Extraction
        precip_list = data.get('precipitation_sum', [0, 0, 0])
        temp_list = data.get('temperature_2m_max', [15, 15, 15])
        wind_list = data.get('wind_speed_10m_max', [10, 10, 10])

        total_raw_rain = sum(precip_list)
        avg_temp = sum(temp_list) / len(temp_list)
        avg_wind = sum(wind_list) / len(wind_list)

        # 2. Drying Efficiency Heuristic
        # We define a "Drying Multiplier" based on Temp (>15C) and Wind (>10km/h)
        # Higher efficiency reduces the 'effective' moisture remaining on ground
        temp_factor = max(0.5, (avg_temp / 20)) # Normalize around 20°C
        wind_factor = max(0.5, (avg_wind / 15)) # Normalize around 15km/h
        drying_efficiency = min(2.0, temp_factor * wind_factor)

        # 3. Adjusted Precipitation Index (API)
        # Net moisture = Rain / Drying Efficiency
        # If it's 25°C and windy, the impact of 10mm of rain is halved.
        adjusted_rain = total_raw_rain / drying_efficiency

        # 4. Refined Non-Linear Surface Coefficients
        # Re-calibrated for non-linear behavior in clay/earth
        soil_sensitivity = {
            "clay": 1.2,    # Heavy saturation, slow drainage
            "dirt": 0.9,
            "earth": 0.9,
            "grass": 0.7,
            "gravel": 0.3,  # Well drained
            "sand": 0.1,    # High permeability
            "asphalt": 0.05 # Almost zero mud risk
        }
        sensitivity = soil_sensitivity.get(surface_type.lower(), 0.7)

        # 5. Final Mud Risk Score Calculation
        mud_score = adjusted_rain * sensitivity

        # Categorization
        if mud_score < 3:
            risk, advice = "Low", "Dry or ideal grip. Fast conditions."
        elif mud_score < 10:
            risk, advice = "Medium", "Damp soil. Slick roots and loose corners possible."
        elif mud_score < 20:
            risk, advice = "High", "Significant mud. Traction loss in steep sections."
        else:
            risk, advice = "Extreme", "Deep saturation. High risk of drivetrain damage and trail erosion."

        return {
            "status": "Success",
            "environmental_context": {
                "raw_rain_72h": f"{total_raw_rain:.1f}mm",
                "avg_temp": f"{avg_temp:.1f}°C",
                "avg_wind_speed": f"{avg_wind:.1f}km/h",
                "drying_efficiency": f"{drying_efficiency:.2f}x"
            },
            "tactical_analysis": {
                "adjusted_moisture_index": round(adjusted_rain, 2),
                "mud_risk_score": risk,
                "surface_detected": surface_type,
                "safety_advice": advice
            }
        }

    except Exception as e:
        return {
            "status": "Error",
            "message": str(e),
            "mud_risk_score": "Unknown"
        }