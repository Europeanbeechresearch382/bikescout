import gpxpy
import requests
import math
import sys
import os
import traceback
import numpy as np
from typing import List, Dict, Any, Optional
from datetime import date
from geopy.distance import geodesic

# Internal tools imports
from bikescout.tools.weather import get_weather_forecast
from bikescout.tools.mud import get_mud_risk_analysis
from bikescout.tools.nutrition import get_nutrition_plan

# --- CONSTANTS ---
GRAVITY = 9.80665

def analyze_track(
        gpx_url: str,
        rider_weight_kg: float,
        bike_weight_kg: float = 7.5,
        pro_intensity: float = 1.6,
        surface_type: str = "road",
        target_date: Optional[str] = None,
        start_hour: Optional[int] = None,
        end_hour: Optional[int] = None
) -> Dict[str, Any]:
    """
    High-fidelity track audit. Processes GPX data, applies weather windowing,
    and calculates performance metrics and tactical insights.
    """
    try:
        # 1. Data Retrieval and Parsing
        # Fetches content from URL or local path
        content = _load_gpx_content(gpx_url)
        gpx = gpxpy.parse(content)

        points = []
        for track in gpx.tracks:
            for segment in track.segments:
                for p in segment.points:
                    if p.elevation is not None:
                        points.append({
                            'lat': p.latitude, 'lon': p.longitude,
                            'ele': p.elevation, 'time': p.time
                        })

        if len(points) < 10:
            return {"status": "Error", "message": "Insufficient data points in GPX for analysis."}

        start_lat, start_lon = points[0]['lat'], points[0]['lon']
        distance_km = round(gpx.length_3d() / 1000, 2)
        total_ascent = round(gpx.get_uphill_downhill().uphill, 1)

        # 2. Advanced Path Analysis
        # Segmentation for gradient analysis and UCI climb identification
        analysis_segments = _process_segments(points, surface_type)
        uci_climbs = _detect_uci_climbs(analysis_segments)

        # 3. Dynamic Weather Windowing
        # Fetches forecast and slices it to match the rider's intended time window
        weather_data = get_weather_forecast(start_lat, start_lon, target_date)

        # Default safety values in case weather service is limited
        ref_temp, ref_wind_speed, ref_wind_dir = 20.0, 10.0, 90

        if weather_data.get("status") == "Success":
            if start_hour is not None and end_hour is not None:
                weather_data = _apply_weather_windowing(weather_data, start_hour, end_hour)

            # Robust key access using .get() to avoid KeyError if data is missing
            ref_cond = weather_data.get("reference_conditions", {})
            ref_temp = ref_cond.get("temp", ref_temp)
            ref_wind_speed = ref_cond.get("wind_speed", ref_wind_speed)
            ref_wind_dir = 90 # Placeholder for advanced wind vectoring

        # 4. Tactical and Environmental Risk Assessment
        tactical_alerts = []
        mud_risk = None

        # Difficulty score based on ascent density and rider intensity profile
        intensity_score = min(100, int((total_ascent / max(distance_km, 1)) * 10 * pro_intensity))

        # Heuristic speed estimation based on surface
        est_speed = 35.0 if surface_type.lower() == "road" else 20.0
        duration_hours = (distance_km / est_speed) + (total_ascent / 1000)

        if surface_type.lower() == "road":
            # Check for crosswind danger zones (echelons)
            tactical_alerts = _calculate_aero_risks(analysis_segments, ref_wind_dir, ref_wind_speed)
        else:
            # Check for terrain saturation risk
            mapped_surface = "gravel" if "gravel" in surface_type.lower() else "dirt"
            mud_risk = get_mud_risk_analysis(start_lat, start_lon, mapped_surface, target_date)

        nutrition_plan = get_nutrition_plan(duration_hours, ref_temp, intensity_score)

        # 5. Performance Modeling
        # Simulation of Power/Weight requirements for key climbs
        performance = _calculate_performance(
            uci_climbs, rider_weight_kg, bike_weight_kg, pro_intensity, ref_temp, ref_wind_speed
        )

        elev_extremes = gpx.get_elevation_extremes()
        max_elevation = getattr(elev_extremes, 'maximum', 0)

        return {
            "status": "Success",
            "mode": surface_type.upper(),
            "target_date": target_date if target_date else date.today().isoformat(),
            "track_metrics": {
                "distance_km": distance_km,
                "total_ascent": total_ascent,
                "max_altitude": round(max_elevation, 1)
            },
            "planning_tools": {
                "weather_forecast": weather_data,
                "nutrition_plan": nutrition_plan,
                "mud_risk": mud_risk
            },
            "climb_analysis": uci_climbs,
            "performance_simulation": performance,
            "tactical_alerts": tactical_alerts,
            "explosivity_zones": _identify_explosivity_zones(analysis_segments, surface_type)
        }

    except Exception as e:
        # Log trace to stderr to keep stdout clean for MCP JSON-RPC protocol
        sys.stderr.write(f"ANALYSIS FAILURE: {traceback.format_exc()}\n")
        return {"status": "Error", "message": f"Track Analysis Failed: {str(e)}"}

def _load_gpx_content(gpx_path: str) -> str:
    """Helper to fetch GPX content from web or local file system."""
    if gpx_path.startswith(('http://', 'https://')):
        res = requests.get(gpx_path, timeout=20)
        res.raise_for_status()
        return res.text
    elif os.path.exists(gpx_path):
        with open(gpx_path, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        raise ValueError(f"GPX source path invalid or unreachable: {gpx_path}")

def _apply_weather_windowing(weather_data: Dict, start: int, end: int) -> Dict:
    """Filters forecast to the active window and calculates mean environmental conditions."""
    filtered_forecast = []
    window_temps = []
    window_winds = []

    # Ensure reference dictionary exists
    if "reference_conditions" not in weather_data:
        weather_data["reference_conditions"] = {}

    # Define visual buffer for context (1h before and after)
    buffer_start, buffer_end = max(0, start - 1), min(23, end + 1)

    for hour_info in weather_data.get("tactical_forecast", []):
        try:
            h_int = int(hour_info["time"].split(":")[0])

            # Slicing the visible forecast for the report
            if buffer_start <= h_int <= buffer_end:
                filtered_forecast.append(hour_info)

            # Numerical aggregation for the performance model
            if start <= h_int <= end:
                # Cleaning string units for numerical processing
                t_val = float(hour_info["temp"].replace("°C", "").strip())
                w_val = float(hour_info["wind"].replace(" km/h", "").strip())
                window_temps.append(t_val)
                window_winds.append(w_val)
        except (ValueError, KeyError):
            continue

    if window_temps:
        avg_temp = round(sum(window_temps) / len(window_temps), 1)
        avg_wind = round(sum(window_winds) / len(window_winds), 1)
        weather_data["reference_conditions"].update({
            "temp": avg_temp,
            "wind_speed": avg_wind,
            "reference_hour": f"Mean average for window {start:02d}-{end:02d}"
        })

    weather_data["tactical_forecast"] = filtered_forecast
    return weather_data

def _process_segments(points: List[Dict], surface: str) -> List[Dict]:
    """Applies smoothing and computes local gradients and bearings for every segment."""
    dist_filter = 15.0 if surface == "road" else 6.0
    grade_cap = 28.0 if surface == "road" else 45.0

    elevations = [p['ele'] for p in points]
    # Simple moving average to reduce GPS vertical jitter
    smoothed_ele = np.convolve(elevations, np.ones(5)/5, mode='same')

    segments = []
    accum_dist, start_idx = 0.0, 0

    for i in range(len(points) - 1):
        p1, p2 = points[i], points[i+1]
        dist = geodesic((p1['lat'], p1['lon']), (p2['lat'], p2['lon'])).meters
        accum_dist += dist

        if accum_dist >= dist_filter:
            # Gradient calculation
            grade = ((smoothed_ele[i+1] - smoothed_ele[start_idx]) / accum_dist) * 100
            grade = max(min(grade, grade_cap), -grade_cap)

            # Vector calculation for bearing (Direction of travel)
            lat1, lon1, lat2, lon2 = map(math.radians, [p1['lat'], p1['lon'], p2['lat'], p2['lon']])
            y = math.sin(lon2 - lon1) * math.cos(lat2)
            x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
            bearing = (math.degrees(math.atan2(y, x)) + 360) % 360

            segments.append({
                'dist': accum_dist, 'grade': grade, 'bearing': bearing,
                'ele_start': smoothed_ele[start_idx], 'ele_end': smoothed_ele[i+1]
            })
            start_idx, accum_dist = i + 1, 0.0
    return segments

def _detect_uci_climbs(segments: List[Dict]) -> List[Dict]:
    """Groups consecutive positive segments into categorized climbs."""
    climbs, current_climb, flat_buffer = [], [], 0
    for s in segments:
        if s['grade'] >= 1.0:
            current_climb.append(s)
            flat_buffer = 0
        elif current_climb:
            # Allow short descents/flats within a climb (1.5km buffer)
            flat_buffer += s['dist']
            current_climb.append(s)
            if flat_buffer > 1500:
                # Trim trailing negative gradient before finalization
                while current_climb and current_climb[-1]['grade'] < 1.0: current_climb.pop()
                _finalize_climb_data(current_climb, segments, climbs)
                current_climb, flat_buffer = [], 0

    if current_climb:
        while current_climb and current_climb[-1]['grade'] < 1.0: current_climb.pop()
        _finalize_climb_data(current_climb, segments, climbs)
    return climbs

def _finalize_climb_data(current_climb, all_segments, climbs_list):
    """Calculates final metrics and difficulty labels for identified climbs."""
    if not current_climb: return

    total_dist = sum(x['dist'] for x in current_climb)
    total_gain = current_climb[-1]['ele_end'] - current_climb[0]['ele_start']

    # Minimum thresholds for a valid climb (500m length, 50m gain)
    if (total_dist > 500 and total_gain > 50):
        avg_grade = (total_gain / total_dist) * 100
        # Difficulty score (modified FIAC/UCI logic)
        score = (total_gain * avg_grade) / 10

        # Determine exact location along the track
        start_idx = all_segments.index(current_climb[0])
        km_start = sum(x['dist'] for x in all_segments[:start_idx]) / 1000

        climbs_list.append({
            "km_start": round(km_start, 1),
            "dist_km": round(total_dist / 1000, 2),
            "gain_m": round(total_gain, 1),
            "avg_grade": round(avg_grade, 1),
            "category": _get_uci_category_label(score, total_gain)
        })

def _get_uci_category_label(score: float, gain: float) -> str:
    """Maps climb score to UCI standard categories."""
    if score >= 650 or gain >= 1000: return "HC"
    if score >= 400 or gain >= 600:  return "Cat 1"
    if score >= 200 or gain >= 350:  return "Cat 2"
    if score >= 80  or gain >= 150:  return "Cat 3"
    return "Cat 4"

def _calculate_performance(climbs, rider_w, bike_w, intensity, temp, wind) -> List[Dict]:
    """Estimates the required W/Kg to climb at professional/targeted pace."""
    results = []
    for c in climbs:
        # Target VAM (Vertical Ascent Meters/Hour) based on category
        vam_target = 1550 if c['category'] == "HC" else 1350 if c['category'] == "Cat 1" else 1100
        total_mass = rider_w + bike_w
        time_hours = c['gain_m'] / vam_target

        # Base power requirement (Physics-based estimation)
        base_power = ((total_mass * GRAVITY * c['gain_m']) / (time_hours * 3600)) * intensity

        # Environmental penalties (Efficiency loss in heat or high wind)
        penalty = (base_power * 0.03 if temp > 28 else 0) + (base_power * 0.02 if wind > 15 else 0)

        results.append({
            "climb": f"Climb @ km {c['km_start']}",
            "category": c['category'],
            "base_wkg": round(base_power / rider_w, 2),
            "weather_adjusted_wkg": round((base_power + penalty) / rider_w, 2)
        })
    return results

def _calculate_aero_risks(segments, wind_dir, wind_speed) -> List[Dict]:
    """Detects dangerous crosswind sections (90deg relative to travel)."""
    alerts = []
    # Sampling segments to avoid alert flooding
    for i in range(0, len(segments), 45):
        s = segments[i]
        rel_angle = abs(s['bearing'] - wind_dir) % 360
        if rel_angle > 180: rel_angle = 360 - rel_angle

        # Echelons usually form with crosswinds between 70 and 110 degrees
        if 70 < rel_angle < 110 and wind_speed > 20:
            dist_at = sum(x['dist'] for x in segments[:i]) / 1000
            alerts.append({
                "km": round(dist_at, 1), "type": "ECHELON RISK",
                "detail": f"{round(wind_speed, 1)}km/h Crosswind at {round(s['bearing'],0)}° heading"
            })
    return alerts[:6]

def _identify_explosivity_zones(segments, surface) -> List[Dict]:
    """Identifies 'Walls' or extremely steep sections for tactical attacks."""
    threshold = 18.0 if surface == "road" else 22.0
    label = "Steep Road Wall" if surface == "road" else "MTB Technical Kick"
    zones = []
    for i, s in enumerate(segments):
        if s['grade'] > threshold:
            dist_at = sum(x['dist'] for x in segments[:i]) / 1000
            zones.append({
                "km": round(dist_at, 2),
                "grade": round(s['grade'], 1),
                "type": label
            })
    return zones[:10]