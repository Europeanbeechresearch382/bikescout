from bikescout.tools.weather import get_weather_forecast
from bikescout.tools.mud import get_mud_risk_analysis

def calculate_ride_windows(lat: float, lon: float, ride_duration_hours: float = 2.0, surface_type: str = "dirt"):
    """
    Tactical Ride Planner: Specifically mapped for BikeScout JSON output.
    Cleans string values (e.g., '93%') and performs sliding window analysis.
    """
    try:
        # --- 1. DATA ACQUISITION ---
        weather_data = get_weather_forecast(lat, lon)
        mud_risk_data = get_mud_risk_analysis(lat, lon, surface_type)

        # --- 2. DATA NORMALIZATION (Cleaning strings like '93%' or '18.3°C') ---
        raw_forecasts = weather_data.get("next_4_hours", [])
        current_mud_score = mud_risk_data.get("mud_risk_score", 0)

        normalized_forecasts = []
        for h in raw_forecasts:
            try:
                # Helper function to strip symbols and convert to float
                def clean_val(v):
                    if isinstance(v, str):
                        return float(v.replace('°C', '').replace('%', '').replace(' km/h', '').strip())
                    return float(v or 0)

                normalized_forecasts.append({
                    "time": h.get("time", "N/A"),
                    "precip_prob": clean_val(h.get("rain_prob", 0)),
                    "wind_speed": clean_val(h.get("wind", 0)),
                    "temp": clean_val(h.get("temp", 15))
                })
            except Exception:
                continue

        # --- 3. VALIDATION ---
        duration_int = int(max(1, ride_duration_hours))
        if not normalized_forecasts:
            return {"status": "Error", "message": "Zero forecast data available."}

        # Cap duration to available data
        if len(normalized_forecasts) < duration_int:
            duration_int = len(normalized_forecasts)

        # --- 4. SLIDING WINDOW ENGINE ---
        best_slot = None
        highest_score = -500.0

        # Thresholds
        MAX_RAIN_PROB = 30
        MAX_WIND_SPEED = 25 # Lowered threshold for tactical safety
        MUD_PENALTY_WEIGHT = 0.6

        for i in range(len(normalized_forecasts) - duration_int + 1):
            window = normalized_forecasts[i : i + duration_int]

            avg_rain = sum(h["precip_prob"] for h in window) / duration_int
            max_wind = max(h["wind_speed"] for h in window)
            avg_temp = sum(h["temp"] for h in window) / duration_int

            # Scoring logic
            current_score = 100.0

            # Severe Rain Penalty (Mission Killer)
            if avg_rain > MAX_RAIN_PROB:
                current_score -= (avg_rain - MAX_RAIN_PROB) * 3
            else:
                current_score -= (avg_rain * 0.5)

            # Wind Penalty
            if max_wind > MAX_WIND_SPEED:
                current_score -= (max_wind - MAX_WIND_SPEED) * 2

            # Mud Saturation Penalty
            current_score -= (current_mud_score * MUD_PENALTY_WEIGHT)

            if current_score > highest_score:
                highest_score = current_score
                best_slot = {
                    "start": window[0]["time"],
                    "end": window[-1]["time"],
                    "score": round(max(0, current_score), 1),
                    "details": {
                        "rain_avg": f"{round(avg_rain)}%",
                        "wind_max": f"{round(max_wind)} km/h",
                        "temp_avg": f"{round(avg_temp)}°C"
                    }
                }

        # --- 5. TACTICAL VERDICT ---
        if highest_score > 75:
            verdict, color = "GO", "GREEN"
        elif highest_score > 40:
            verdict, color = "CAUTION", "YELLOW"
        else:
            verdict, color = "NO-GO", "RED"

        return {
            "payload_version": "1.0",
            "status": "Success",
            "planner_report": {
                "verdict": verdict,
                "tactical_color": color,
                "confidence_score": f"{best_slot['score']}/100",
                "best_window": f"{best_slot['start']} - {best_slot['end']}",
                "environmental_briefing": best_slot["details"],
                "mud_risk_impact": f"{current_mud_score}%"
            }
        }

    except Exception as e:
        return {"status": "Error", "message": f"Planner failed: {str(e)}"}