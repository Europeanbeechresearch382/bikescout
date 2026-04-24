import gpxpy
import requests
import math
import sys
import os
import traceback
import numpy as np
from typing import Literal
from datetime import datetime, date, timedelta, timezone
from geopy.distance import geodesic
from bikescout.tools.weather import get_weather_forecast
from bikescout.tools.mud import get_mud_risk_analysis
from bikescout.tools.nutrition import get_nutrition_plan

class ProCyclingEngine:
    """
    Advanced Pro-Cycling Engine for high-fidelity track analysis.
    Supports UCI climb categorization, VAM (Vertical Ascent Meters/h),
    and predictive Weather, Mud, and Nutrition planning based on target dates.
    """

    def __init__(self, ors_key=None):
        self.ors_key = ors_key
        self.gravity = 9.80665

    def _load_gpx_content(self, gpx_path):
        """Loads GPX content from either a remote URL or a local file path."""
        if gpx_path.startswith(('http://', 'https://')):
            res = requests.get(gpx_path, timeout=20)
            res.raise_for_status()
            return res.text
        elif os.path.exists(gpx_path):
            with open(gpx_path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            raise ValueError(f"GPX source not found: {gpx_path}")

    def analyze_gpx_track(self, gpx_url, rider_weight, bike_weight=7.5, pro_intensity=1.6, surface_type="road", target_date=None, start_hour=None, end_hour=None):
        """
        Main entry point for professional track audit and predictive planning.
        """
        try:
            # 1. Load and Parse GPX data
            content = self._load_gpx_content(gpx_url)
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
                return {"status": "Error", "message": "Insufficient points for analysis."}

            start_lat, start_lon = points[0]['lat'], points[0]['lon']
            distance_km = round(gpx.length_3d() / 1000, 2)
            total_ascent = round(gpx.get_uphill_downhill().uphill, 1)

            # 2. Segment Processing & UCI Climbs
            analysis_segments = self._process_segments(points, surface_type)
            uci_climbs = self._detect_uci_climbs(analysis_segments)

            # 3. Dynamic Weather Analysis (Window-Based)
            # We fetch the forecast for the target date
            weather_data = get_weather_forecast(start_lat, start_lon, target_date)

            if weather_data["status"] == "Success":
                # Check if specific race hours were passed
                if start_hour is not None and end_hour is not None:
                    filtered_forecast = []
                    window_temps = []
                    window_winds = []

                    # Define buffer: 1 hour before and 1 hour after
                    buffer_start = max(0, start_hour - 1)
                    buffer_end = min(23, end_hour + 1)

                    for hour_info in weather_data.get("tactical_forecast", []):
                        h_int = int(hour_info["time"].split(":")[0])
                        # A. Apply 1h buffer filter for the OUTPUT mapping
                        if buffer_start <= h_int <= buffer_end:
                            filtered_forecast.append(hour_info)
                        if start_hour <= h_int <= end_hour:
                            window_temps.append(float(hour_info["temp"].replace("°C", "")))
                            window_winds.append(float(hour_info["wind"].replace(" km/h", "")))

                    # Update weather_data with the mapped/filtered list
                    weather_data["tactical_forecast"] = filtered_forecast

                    if window_temps:
                        ref_temp = sum(window_temps) / len(window_temps)
                        ref_wind_speed = sum(window_winds) / len(window_winds)
                        weather_data["reference_conditions"].update({
                            "temp": round(ref_temp, 1),
                            "wind_speed": round(ref_wind_speed, 1),
                            "reference_hour": f"Average {start_hour}-{end_hour}"
                        })
                    else:
                        # Fallback if window is outside the provided forecast range
                        ref_temp = weather_data["reference_conditions"]["temp"]
                        ref_wind_speed = weather_data["reference_conditions"]["wind_speed"]
                else:
                    # Default: Use the reference hour determined by get_weather_forecast
                    ref_temp = weather_data["reference_conditions"]["temp"]
                    ref_wind_speed = weather_data["reference_conditions"]["wind_speed"]

                ref_wind_dir = 90
            else:
                ref_temp, ref_wind_speed, ref_wind_dir = 20.0, 10.0, 90

            # 4. Mode-Based Conditional Analysis
            tactical_alerts = []
            mud_risk = None

            # Calculate Intensity Score (0-100 scale based on gradient and pro_intensity)
            intensity_score = min(100, int((total_ascent / max(distance_km, 1)) * 10 * pro_intensity))

            # Estimate Duration (Rough pro speeds: 35km/h road, 20km/h mtb)
            est_speed = 35.0 if surface_type == "road" else 20.0
            duration_hours = (distance_km / est_speed) + (total_ascent / 1000)

            if surface_type.lower() == "road":
                # ROAD: Skip Mud Tool, execute Wind Audit and Hydration
                tactical_alerts = self._calculate_aero_risks(analysis_segments, ref_wind_dir, ref_wind_speed)
                nutrition_plan = get_nutrition_plan(duration_hours, ref_temp, intensity_score)
            else:
                # MTB/GRAVEL: Execute Mud Tool, skip specific road echelon audit
                mapped_surface = "gravel" if "gravel" in surface_type.lower() else "dirt"
                mud_risk = get_mud_risk_analysis(start_lat, start_lon, mapped_surface, target_date)
                nutrition_plan = get_nutrition_plan(duration_hours, ref_temp, intensity_score)

            # 5. Performance Simulation
            performance = self._calculate_performance(
                uci_climbs, rider_weight, bike_weight, pro_intensity, ref_temp, ref_wind_speed
            )

            # Max elevation safety check
            elev_extremes = gpx.get_elevation_extremes()
            max_elevation = getattr(elev_extremes, 'maximum', None)
            if max_elevation is None and elev_extremes:
                max_elevation = elev_extremes[1]

            return {
                "status": "Success",
                "mode": surface_type.upper(),
                "target_date": target_date if target_date else date.today().isoformat(),
                "track_metrics": {
                    "distance_km": distance_km,
                    "total_ascent": total_ascent,
                    "max_altitude": round(max_elevation, 1) if max_elevation is not None else 0
                },
                "planning_tools": {
                    "weather_forecast": weather_data,
                    "nutrition_plan": nutrition_plan,
                    "mud_risk": mud_risk
                },
                "climb_analysis": uci_climbs,
                "performance_simulation": performance,
                "tactical_alerts": tactical_alerts,
                "explosivity_zones": self._identify_explosivity_zones(analysis_segments, surface_type)
            }

        except Exception as e:
            sys.stderr.write(f"PRO-ENGINE FAILURE: {traceback.format_exc()}\n")
            return {"status": "Error", "message": str(e)}

    def _process_segments(self, points, surface_type):
        dist_filter = 15.0 if surface_type == "road" else 6.0
        grade_cap = 28.0 if surface_type == "road" else 45.0

        elevations = [p['ele'] for p in points]
        window_size = 5
        smoothed_ele = np.convolve(elevations, np.ones(window_size)/window_size, mode='same')

        segments = []
        accumulated_dist = 0.0
        start_idx = 0

        for i in range(len(points) - 1):
            p1, p2 = points[i], points[i+1]
            dist = geodesic((p1['lat'], p1['lon']), (p2['lat'], p2['lon'])).meters
            accumulated_dist += dist

            if accumulated_dist >= dist_filter:
                elev_diff = smoothed_ele[i+1] - smoothed_ele[start_idx]
                grade = (elev_diff / accumulated_dist) * 100
                grade = max(min(grade, grade_cap), -grade_cap)

                lat1, lon1 = math.radians(p1['lat']), math.radians(p1['lon'])
                lat2, lon2 = math.radians(p2['lat']), math.radians(p2['lon'])
                d_lon = lon2 - lon1
                y = math.sin(d_lon) * math.cos(lat2)
                x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
                bearing = (math.degrees(math.atan2(y, x)) + 360) % 360

                segments.append({
                    'dist': accumulated_dist,
                    'grade': grade,
                    'bearing': bearing,
                    'ele_start': smoothed_ele[start_idx],
                    'ele_end': smoothed_ele[i+1]
                })

                start_idx = i + 1
                accumulated_dist = 0.0

        return segments

    def _detect_uci_climbs(self, segments):
        climbs = []
        current_climb = []
        flat_buffer = 0
        flat_buffer_max = 1500

        for s in segments:
            if s['grade'] >= 1.0:
                current_climb.append(s)
                flat_buffer = 0
            elif current_climb:
                flat_buffer += s['dist']
                current_climb.append(s)
                if flat_buffer > flat_buffer_max:
                    while current_climb and current_climb[-1]['grade'] < 1.0:
                        current_climb.pop()
                    self._finalize_climb(current_climb, segments, climbs)
                    current_climb = []
                    flat_buffer = 0

        if current_climb:
            while current_climb and current_climb[-1]['grade'] < 1.0:
                current_climb.pop()
            if current_climb:
                self._finalize_climb(current_climb, segments, climbs)

        return climbs

    def _finalize_climb(self, current_climb, all_segments, climbs_list):
        total_dist = sum(x['dist'] for x in current_climb)
        total_gain = current_climb[-1]['ele_end'] - current_climb[0]['ele_start']

        if (total_dist > 1500 and total_gain > 80) or (total_dist > 500 and total_gain > 50):
            avg_grade = (total_gain / total_dist) * 100
            score = (total_gain * avg_grade) / 10
            start_idx = all_segments.index(current_climb[0])
            km_start = sum(x['dist'] for x in all_segments[:start_idx]) / 1000

            climbs_list.append({
                "km_start": round(km_start, 1),
                "dist_km": round(total_dist / 1000, 2),
                "gain_m": round(total_gain, 1),
                "avg_grade": round(avg_grade, 1),
                "category": self._get_uci_cat(score, total_gain)
            })

    def _get_uci_cat(self, score, gain):
        if score >= 650 or gain >= 1000: return "HC"
        if score >= 400 or gain >= 600:  return "Cat 1"
        if score >= 200 or gain >= 350:  return "Cat 2"
        if score >= 80  or gain >= 150:  return "Cat 3"
        return "Cat 4"

    def _calculate_performance(self, climbs, rider_w, bike_w, intensity, temp_c, wind_speed):
        results = []
        for c in climbs:
            vam_target = 1550 if c['category'] == "HC" else 1350 if c['category'] == "Cat 1" else 1100
            total_mass = rider_w + bike_w
            time_hours = c['gain_m'] / vam_target
            work_joules = total_mass * self.gravity * c['gain_m']

            base_power = (work_joules / (time_hours * 3600)) * intensity

            weather_penalty = 0
            if temp_c > 28: weather_penalty += base_power * 0.03
            if wind_speed > 15: weather_penalty += base_power * 0.02

            total_power = base_power + weather_penalty

            results.append({
                "climb": f"Climb @ km {c['km_start']}",
                "category": c['category'],
                "base_wkg": round(base_power / rider_w, 2),
                "weather_adjusted_wkg": round(total_power / rider_w, 2)
            })
        return results

    def _calculate_aero_risks(self, segments, wind_dir, wind_speed):
        alerts = []
        for i in range(0, len(segments), 45):
            s = segments[i]
            rel_angle = abs(s['bearing'] - wind_dir) % 360
            if rel_angle > 180: rel_angle = 360 - rel_angle

            if 70 < rel_angle < 110 and wind_speed > 20:
                dist_at = sum(x['dist'] for x in segments[:i]) / 1000
                alerts.append({
                    "km": round(dist_at, 1),
                    "type": "ECHELON RISK",
                    "detail": f"{round(wind_speed, 1)}km/h Crosswind at {round(s['bearing'],0)}° heading"
                })
        return alerts[:6]

    def _identify_explosivity_zones(self, segments, surface_type):
        threshold = 18.0 if surface_type == "road" else 22.0
        label = "Steep Road Wall" if surface_type == "road" else "MTB Technical Kick"

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