from datetime import datetime, timedelta, timezone, date
from pysolar.solar import get_altitude
from typing import Literal
import requests


OPEN_METEO_ARCHIVE_URL = 'https://archive-api.open-meteo.com/v1/archive'


def get_shadow_penalty(lat, lon):
    """
    Calculates the Solar Evaporation Penalty based on sun altitude.
    Low sun angles (winter or late afternoon) significantly reduce trail drying speed.
    """
    try:
        now = datetime.now(timezone.utc)
        altitude = get_altitude(lat, lon, now)

        # Heuristic: Sun below 20° provides minimal drying energy (Shadow Lock)
        if altitude < 20:
            return 0.4  # 60% reduction in drying efficiency
        elif altitude < 40:
            return 0.7  # 30% reduction in drying efficiency
        return 1.0      # Full solar potential
    except Exception:
        return 1.0      # Neutral fallback

from datetime import datetime, timedelta, timezone
import requests

def get_mud_risk_analysis(
        lat: float,
        lon: float,
        surface_type: Literal["dirt", "gravel", "clay"] = "dirt",
        target_date: str = None):
    """
    Tactical Mud Risk Analysis v2.5: Dynamic TAEL (Terrain-Aware Evaporation Lag) Model.
    Now supports historical analysis, real-time scouting, and future race-day predictions.

    If target_date is provided, the model analyzes the 72h window preceding that specific date
    to determine ground saturation at the start of the event.
    """
    try:
        # 1. Temporal Window Logic
        # If target_date is provided, we center the 72h window on it.
        # Otherwise, we use 'now' as the reference point.
        if target_date:
            reference_date = datetime.strptime(target_date, "%Y-%m-%d").date()
        else:
            reference_date = datetime.now().date()

        # The 72h look-back window is critical to calculate cumulative ground saturation
        end_date = reference_date
        start_date = end_date - timedelta(days=3)

        # 2. Data Acquisition (Open-Meteo Archive or Forecast)
        # Note: Archive API is used for past/current dates.
        # For future dates, the regular Forecast API should be used.
        # For simplicity in this logic, we use the archive/forecast logic:
        url = "https://archive-api.open-meteo.com/v1/archive"
        if reference_date > datetime.now().date():
            # Switch to forecast API if the date is in the future
            url = "https://api.open-meteo.com/v1/forecast"

        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "daily": ["precipitation_sum", "temperature_2m_max", "wind_speed_10m_max"],
            "timezone": "auto"
        }

        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json().get('daily', {})

        # 3. Environmental Data Extraction
        precip_list = data.get('precipitation_sum', [0, 0, 0])
        temp_list = data.get('temperature_2m_max', [15, 15, 15])
        wind_list = data.get('wind_speed_10m_max', [10, 10, 10])

        total_raw_rain = sum(precip_list)
        avg_temp = sum(temp_list) / max(len(temp_list), 1)
        avg_wind = sum(wind_list) / max(len(wind_list), 1)

        # 4. Drying Efficiency Heuristic
        # Thermal & Kinetic factors affect how fast the trail "heals"
        temp_factor = max(0.5, (avg_temp / 20))
        wind_factor = max(0.5, (avg_wind / 15))

        # Integration of Shadow Persistence (Solar Angle based on coordinates)
        shadow_penalty = get_shadow_penalty(lat, lon)
        drying_efficiency = min(2.0, temp_factor * wind_factor * shadow_penalty)

        # 5. Adjusted Moisture Index
        # Effective moisture is raw rain dampened by drying efficiency
        adjusted_rain = total_raw_rain / max(0.1, drying_efficiency)

        # 6. Terrain Sensitivity
        soil_sensitivity = {
            "clay": 1.2, "dirt": 0.9, "earth": 0.9, "grass": 0.7,
            "gravel": 0.3, "sand": 0.1, "asphalt": 0.05
        }
        sensitivity = soil_sensitivity.get(surface_type.lower(), 0.7)

        # 7. Final Score & Categorization
        mud_score_numeric = adjusted_rain * sensitivity

        if mud_score_numeric < 3:
            risk, advice = "Low", "Optimal grip. Surface is stable and fast."
        elif mud_score_numeric < 10:
            risk, advice = "Medium", "Damp sections. Expect reduced traction on technical off-cambers."
        elif mud_score_numeric < 20:
            risk, advice = "High", "Significant saturation. High risk of sliding in technical sectors."
        else:
            risk, advice = "Extreme", "Total saturation. Trail damage likely. Race conditions will be brutal."

        # 8. Output Intel
        # For the solar altitude, we use the reference_date at noon
        noon_ref = datetime.combine(reference_date, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(hours=12)

        return {
            "status": "Success",
            "metadata": {
                "target_date": reference_date.isoformat(),
                "is_predictive": reference_date > datetime.now().date()
            },
            "environmental_context": {
                "cumulative_rain_72h": f"{total_raw_rain:.1f}mm",
                "avg_temp": f"{avg_temp:.1f}°C",
                "drying_efficiency": f"{drying_efficiency:.2f}x",
                "solar_altitude": f"{get_altitude(lat, lon, noon_ref):.1f}°"
            },
            "tactical_analysis": {
                "adjusted_moisture_index": round(adjusted_rain, 2),
                "mud_risk_score": risk,
                "mud_risk_numeric": round(mud_score_numeric, 1),
                "surface_type": surface_type,
                "safety_advice": advice
            }
        }

    except Exception as e:
        return {
            "status": "Error",
            "message": f"Telemetry failure: {str(e)}",
            "mud_risk_score": "Unknown"
        }