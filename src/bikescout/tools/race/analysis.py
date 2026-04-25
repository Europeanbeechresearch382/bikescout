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
AIR_DENSITY = 1.225 # kg/m^3 (approximate at sea level)
CRR_ROAD = 0.004    # Rolling resistance coefficient for road
CDA_CLIMB = 0.35    # Aerodynamic drag coefficient for climbing position

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
    and calculates performance metrics and tactical insights using a physics-based model.
    """
    try:
        # 1. Data Retrieval and Parsing
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
            return {"status": "Error", "message": "Insufficient data points in GPX."}

        start_lat, start_lon = points[0]['lat'], points[0]['lon']
        distance_km = round(gpx.length_3d() / 1000, 2)
        total_ascent = round(gpx.get_uphill_downhill().uphill, 1)

        # 2. Path Analysis with Cold Start protection and smoothing
        analysis_segments = _process_segments(points, surface_type)
        uci_climbs = _detect_uci_climbs(analysis_segments)

        # 3. Dynamic Weather Windowing
        weather_data = get_weather_forecast(start_lat, start_lon, target_date)
        ref_temp, ref_wind_speed, ref_wind_dir = 20.0, 10.0, 90

        if weather_data.get("status") == "Success":
            if start_hour is not None and end_hour is not None:
                weather_data = _apply_weather_windowing(weather_data, start_hour, end_hour)

            ref_cond = weather_data.get("reference_conditions", {})
            ref_temp = ref_cond.get("temp", ref_temp)
            ref_wind_speed = ref_cond.get("wind_speed", ref_wind_speed)
            ref_wind_dir = ref_cond.get("wind_dir_degrees", ref_wind_dir)

        # 4. Tactical and Environmental Assessment
        tactical_alerts = []
        mud_risk = None
        intensity_score = min(100, int((total_ascent / max(distance_km, 1)) * 10 * pro_intensity))

        est_speed = 35.0 if surface_type.lower() == "road" else 20.0
        duration_hours = (distance_km / est_speed) + (total_ascent / 1000)

        if surface_type.lower() == "road":
            tactical_alerts = _calculate_aero_risks(analysis_segments, ref_wind_dir, ref_wind_speed)
        else:
            mapped_surface = "gravel" if "gravel" in surface_type.lower() else "dirt"
            mud_risk = get_mud_risk_analysis(start_lat, start_lon, mapped_surface, target_date)

        nutrition_plan = get_nutrition_plan(duration_hours, ref_temp, intensity_score)

        # 5. Performance Simulation
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
            "tactical_zones": _identify_tactical_zones(analysis_segments, surface_type, uci_climbs)
        }

    except Exception as e:
        sys.stderr.write(f"ANALYSIS FAILURE: {traceback.format_exc()}\n")
        return {"status": "Error", "message": f"Track Analysis Failed: {str(e)}"}

def _load_gpx_content(gpx_path: str) -> str:
    """Fetches GPX content from web or local file system."""
    if gpx_path.startswith(('http://', 'https://')):
        res = requests.get(gpx_path, timeout=20)
        res.raise_for_status()
        return res.text
    elif os.path.exists(gpx_path):
        with open(gpx_path, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        raise ValueError(f"GPX source invalid: {gpx_path}")

def _apply_weather_windowing(weather_data: Dict, start: int, end: int) -> Dict:
    """Averages weather metrics within the specified time window."""
    filtered_forecast = []
    window_temps, window_winds, window_dirs = [], [], []

    if "reference_conditions" not in weather_data:
        weather_data["reference_conditions"] = {}

    buffer_start, buffer_end = max(0, start - 1), min(23, end + 1)

    for hour_info in weather_data.get("tactical_forecast", []):
        try:
            h_int = int(hour_info["time"].split(":")[0])
            if buffer_start <= h_int <= buffer_end:
                filtered_forecast.append(hour_info)

            if start <= h_int <= end:
                t_val = float(hour_info["temp"].replace("°C", "").replace("C", "").strip())
                w_val = float(hour_info["wind"].replace(" km/h", "").strip())
                w_dir = hour_info.get("wind_dir", 90)
                window_temps.append(t_val)
                window_winds.append(w_val)
                window_dirs.append(w_dir)
        except (ValueError, KeyError):
            continue

    if window_temps:
        weather_data["reference_conditions"].update({
            "temp": round(sum(window_temps) / len(window_temps), 1),
            "wind_speed": round(sum(window_winds) / len(window_winds), 1),
            "wind_dir_degrees": int(sum(window_dirs) / len(window_dirs)),
            "reference_hour": f"Calculated window {start:02d}-{end:02d}"
        })

    weather_data["tactical_forecast"] = filtered_forecast
    return weather_data

def _process_segments(points: List[Dict], surface: str) -> List[Dict]:
    """Processes raw points into smoothed distance/grade segments."""
    dist_filter = 25.0 if surface == "road" else 15.0
    grade_cap = 25.0 if surface == "road" else 35.0

    elevations = [p['ele'] for p in points]
    window_size = 10
    smoothed_ele = np.convolve(elevations, np.ones(window_size)/window_size, mode='same')

    segments = []
    accum_dist, total_elapsed_dist, start_idx = 0.0, 0.0, 0

    for i in range(len(points) - 1):
        p1, p2 = points[i], points[i+1]
        dist = geodesic((p1['lat'], p1['lon']), (p2['lat'], p2['lon'])).meters
        accum_dist += dist
        total_elapsed_dist += dist

        if accum_dist >= dist_filter:
            ele_diff = smoothed_ele[i+1] - smoothed_ele[start_idx]
            grade = (ele_diff / accum_dist) * 100

            # --- COLD START PROTECTION ---
            if total_elapsed_dist < 500:
                grade = max(min(grade, 8.0), -8.0)
            else:
                grade = max(min(grade, grade_cap), -grade_cap)

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
    """Isolates significant uphill sections and categories them."""
    climbs, current_climb, flat_buffer = [], [], 0
    for s in segments:
        if s['grade'] >= 1.5:
            current_climb.append(s)
            flat_buffer = 0
        elif current_climb:
            flat_buffer += s['dist']
            current_climb.append(s)
            if flat_buffer > 1000:
                while current_climb and current_climb[-1]['grade'] < 1.0: current_climb.pop()
                _finalize_climb_data(current_climb, segments, climbs)
                current_climb, flat_buffer = [], 0

    if current_climb:
        while current_climb and current_climb[-1]['grade'] < 1.0: current_climb.pop()
        _finalize_climb_data(current_climb, segments, climbs)
    return climbs

def _finalize_climb_data(current_climb, all_segments, climbs_list):
    """Calculates final metrics for a climb with Pro-Tour filtering logic."""
    if not current_climb: return

    total_dist = sum(x['dist'] for x in current_climb)
    total_gain = current_climb[-1]['ele_end'] - current_climb[0]['ele_start']
    avg_grade = (total_gain / total_dist) * 100

    # --- PRO-TOUR FILTERING ---
    # Discard shallow climbs (<3.5%) unless they have significant gain (>250m)
    if avg_grade < 3.5 and total_gain < 250:
        return

    # Basic physical threshold for categorized climbs
    if total_dist > 1500 and total_gain > 100:
        score = (total_gain * avg_grade) / 10
        start_idx = all_segments.index(current_climb[0])
        km_start = sum(x['dist'] for x in all_segments[:start_idx]) / 1000

        climbs_list.append({
            "km_start": round(km_start, 1),
            "dist_km": round(total_dist / 1000, 2),
            "gain_m": round(total_gain, 1),
            "avg_grade": round(avg_grade, 1),
            "category": _get_uci_category_label(score, total_gain, total_dist)
        })

def _get_uci_category_label(score: float, gain: float, dist: float) -> str:
    """Maps climb difficulty score to UCI standard categories."""
    if score >= 800 or gain >= 1000: return "HC"
    if score >= 400 or gain >= 600:  return "Cat 1"
    if score >= 200 or gain >= 350:  return "Cat 2"
    if (score >= 100 or gain >= 150) and dist > 2500: return "Cat 3"
    return "Cat 4"

def _calculate_performance(climbs, rider_w, bike_w, intensity, temp, wind_speed) -> List[Dict]:
    """Physics model to solve required W/Kg and estimated time/VAM."""
    results = []
    total_mass = rider_w + bike_w
    target_wkg = 3.8 * intensity
    target_power = target_wkg * rider_w

    for c in climbs:
        grade_decimal = c['avg_grade'] / 100
        theta = math.atan(grade_decimal)

        v_mps = 2.0
        for _ in range(10):
            f_grav = total_mass * GRAVITY * math.sin(theta)
            f_roll = total_mass * GRAVITY * math.cos(theta) * CRR_ROAD
            f_aero = 0.5 * AIR_DENSITY * CDA_CLIMB * (v_mps ** 2)
            p_total = v_mps * (f_grav + f_roll + f_aero)
            dp_dv = f_grav + f_roll + 1.5 * AIR_DENSITY * CDA_CLIMB * (v_mps ** 2)
            v_mps = v_mps - (p_total - target_power) / dp_dv

        speed_kmh = max(v_mps * 3.6, 5.0)
        time_hours = c['dist_km'] / speed_kmh
        vam = c['gain_m'] / time_hours

        # Environmental W/Kg adjustments
        penalty = (target_power * 0.03 if temp > 28 else 0) + (target_power * 0.02 if wind_speed > 15 else 0)
        adj_wkg = (target_power + penalty) / rider_w

        results.append({
            "climb": f"Climb @ km {c['km_start']} ({c['category']})",
            "est_time_min": round(time_hours * 60, 1),
            "est_vam": round(vam),
            "target_wkg": round(target_wkg, 2),
            "weather_adjusted_wkg": round(adj_wkg, 2)
        })
    return results

def _calculate_aero_risks(segments, wind_dir, wind_speed) -> List[Dict]:
    """Identifies potential echelon formation zones."""
    alerts = []
    for i in range(0, len(segments), 45):
        s = segments[i]
        rel_angle = abs(s['bearing'] - wind_dir) % 360
        if rel_angle > 180: rel_angle = 360 - rel_angle

        if 60 < rel_angle < 120 and wind_speed > 20:
            dist_at = sum(x['dist'] for x in segments[:i]) / 1000
            alerts.append({
                "km": round(dist_at, 1), "type": "ECHELON RISK",
                "detail": f"{round(wind_speed, 1)}km/h Crosswind at {round(s['bearing'],0)}°"
            })
    return alerts[:6]

def _identify_tactical_zones(segments, surface, uci_climbs) -> List[Dict]:
    zones = []

    for c in uci_climbs:
        if c['category'] in ['Cat 1', 'HC']:
            zones.append({
                "km": round(c['km_start'] - 0.9, 2),
                "grade": c['avg_grade'],
                "type": f"CRITICAL POSITIONING: {c['category']} Entrance"
            })

    curr_d = 0.0
    for s in segments:
        curr_d += s['dist']
        km = curr_d / 1000


        is_major = any(c['km_start'] <= km <= (c['km_start'] + c['dist_km'])
                       for c in uci_climbs if c['category'] in ['Cat 1', 'HC'])

        up_trigger = 11.0 if is_major else 13.5
        down_trigger = -13.0

        if s['grade'] > up_trigger:
            zones.append({
                "km": round(km, 2), "grade": round(s['grade'], 1),
                "type": "Attack Zone / Selection Point" if is_major else "Explosive Wall"
            })
        elif s['grade'] < down_trigger:
            zones.append({
                "km": round(km, 2), "grade": round(s['grade'], 1),
                "type": "Steep Technical Descent"
            })

    final = []
    last_km = -5.0

    sorted_zones = sorted(zones, key=lambda x: (x['km'], "Positioning" not in x['type']))

    for z in sorted_zones:
        if z['km'] - last_km > 0.7: 
            final.append(z)
            last_km = z['km']

    return final