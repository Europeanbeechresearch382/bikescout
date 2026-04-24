import gpxpy
import requests
import math
import sys
import os
import traceback
import numpy as np
from datetime import datetime
from geopy.distance import geodesic

class ProCyclingEngine:
    """
    Advanced Pro-Cycling Engine for high-fidelity track analysis.
    Supports UCI climb categorization, VAM (Vertical Ascent Meters/h),
    and Crosswind Echelon Risk detection with specialized Road/MTB filtering.
    """

    def __init__(self, ors_key, weather_api="https://api.open-meteo.com/v1/forecast"):
        self.ors_key = ors_key
        self.weather_api = weather_api
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

    def analyze_gpx_track(self, gpx_url, rider_weight, bike_weight=7.5, pro_intensity=1.6, surface_type="road"):
        """
        Main entry point for professional track audit.

        Args:
            gpx_url (str): URL or local path to GPX file.
            rider_weight (float): Rider mass in kg.
            bike_weight (float): Bike mass in kg.
            pro_intensity (float): Multiplier for effort simulation (1.0 - 2.0).
            surface_type (str): "road" or "mtb". Adjusts jitter filtering and grade caps.
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

            # 2. Sequential Segment Processing (with adaptive Road/MTB filters)
            analysis_segments = self._process_segments(points, surface_type)

            # 3. UCI Climb Detection & Categorization
            uci_climbs = self._detect_uci_climbs(analysis_segments)

            # 4. Tactical Weather Overlay (Aero/Crosswind Risk)
            weather_data = self._get_track_weather(points[0])
            tactical_alerts = self._calculate_aero_risks(analysis_segments, weather_data)

            # 5. Performance Simulation (VAM & Power Requirements)
            performance = self._calculate_performance(
                uci_climbs, rider_weight, bike_weight, pro_intensity
            )

            # 6. Extract Global Elevation Extremes (Safety Check for gpxpy version)
            elev_extremes = gpx.get_elevation_extremes()
            max_elevation = getattr(elev_extremes, 'maximum', None)
            if max_elevation is None and elev_extremes:
                max_elevation = elev_extremes[1]

            return {
                "status": "Success",
                "mode": surface_type.upper(),
                "track_metrics": {
                    "distance_km": round(gpx.length_3d() / 1000, 2),
                    "total_ascent": round(gpx.get_uphill_downhill().uphill, 1),
                    "max_altitude": round(max_elevation, 1) if max_elevation is not None else 0
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
        """
        Cleans and normalizes GPS data into logical track segments.

        Uses distance accumulation instead of dropping points. This preserves
        the total race distance and prevents artificial gradient spikes, ensuring
        that the calculated slope matches real-world road conditions.
        """
        # Distance threshold to group points and safety caps for unrealistic gradients
        dist_filter = 15.0 if surface_type == "road" else 6.0
        grade_cap = 28.0 if surface_type == "road" else 45.0

        # Elevation Smoothing: Apply a Simple Moving Average (SMA) window of 5 points
        # to mitigate barometric or GPS altitude noise.
        elevations = [p['ele'] for p in points]
        window_size = 5
        smoothed_ele = np.convolve(elevations, np.ones(window_size)/window_size, mode='same')

        segments = []
        accumulated_dist = 0.0
        start_idx = 0

        for i in range(len(points) - 1):
            p1, p2 = points[i], points[i+1]
            # Calculate high-precision distance between coordinates
            dist = geodesic((p1['lat'], p1['lon']), (p2['lat'], p2['lon'])).meters
            accumulated_dist += dist

            # Create a segment only once the minimum distance threshold is met
            if accumulated_dist >= dist_filter:
                elev_diff = smoothed_ele[i+1] - smoothed_ele[start_idx]
                grade = (elev_diff / accumulated_dist) * 100

                # Apply Safety Cap to prevent outliers
                grade = max(min(grade, grade_cap), -grade_cap)

                # Tactical Bearing calculation (Compass heading for wind analysis)
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
                    'ele_end': smoothed_ele[i+1],
                    'lat': points[start_idx]['lat'],
                    'lon': points[start_idx]['lon']
                })

                # Reset accumulation for the next tactical segment
                start_idx = i + 1
                accumulated_dist = 0.0

        return segments

    def _detect_uci_climbs(self, segments):
        """
        Groups segments into continuous climbs using professional racing logic.

        Implements an 'Elastic Buffer' (up to 1500m) to tolerate plateaus
        and minor descents often found in iconic climbs (e.g., Oropa or Alpe d'Huez).
        """
        climbs = []
        current_climb = []
        flat_buffer = 0
        flat_buffer_max = 1500  # 1.5km tolerance for plateaus/false flats

        for s in segments:
            if s['grade'] >= 1.0: # Threshold for active climbing
                current_climb.append(s)
                flat_buffer = 0
            elif current_climb:
                # Potential plateau detected; temporarily sustain the climb
                flat_buffer += s['dist']
                current_climb.append(s)

                if flat_buffer > flat_buffer_max:
                    # Plateau too long; end the climb and trim trailing flat segments
                    while current_climb and current_climb[-1]['grade'] < 1.0:
                        current_climb.pop()

                    self._finalize_climb(current_climb, segments, climbs)
                    current_climb = []
                    flat_buffer = 0

        # Close any active climb at the end of the track (e.g., Summit Finishes)
        if current_climb:
            while current_climb and current_climb[-1]['grade'] < 1.0:
                current_climb.pop()
            if current_climb:
                self._finalize_climb(current_climb, segments, climbs)

        return climbs

    def _finalize_climb(self, current_climb, all_segments, climbs_list):
        """
        Calculates the official UCI Score and metadata for a verified climb.
        """
        total_dist = sum(x['dist'] for x in current_climb)
        total_gain = current_climb[-1]['ele_end'] - current_climb[0]['ele_start']

        # Professional filters: Climb must be >1.5km or a significant 'Muro' (Wall)
        if (total_dist > 1500 and total_gain > 80) or (total_dist > 500 and total_gain > 50):
            avg_grade = (total_gain / total_dist) * 100
            # Classic UCI Intensity Score formula
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
        """
        Categorizes climbs based on modern ASO/RCS Grand Tour metrics.

        Calibrated for 2024/2026 World Tour standards
        """
        if score >= 650 or gain >= 1000: return "HC"
        if score >= 400 or gain >= 600:  return "Cat 1"
        if score >= 200 or gain >= 350:  return "Cat 2"
        if score >= 80  or gain >= 150:  return "Cat 3"
        return "Cat 4"

    def _calculate_performance(self, climbs, rider_w, bike_w, intensity):
        """Estimates Watts and Watts/kg required at Pro-Tour speeds (VAM)."""
        results = []
        for c in climbs:
            # Pro-level VAM targets
            vam_target = 1550 if c['category'] == "HC" else 1350 if c['category'] == "Cat 1" else 1100

            total_mass = rider_w + bike_w
            time_hours = c['gain_m'] / vam_target
            work_joules = total_mass * self.gravity * c['gain_m']

            # Simulation including aero/mechanical friction (Intensity multiplier)
            total_power = (work_joules / (time_hours * 3600)) * intensity

            results.append({
                "climb": f"Climb @ km {c['km_start']}",
                "category": c['category'],
                "target_vam": vam_target,
                "power_required_watts": round(total_power, 1),
                "watts_per_kg": round(total_power / rider_w, 2)
            })
        return results

    def _calculate_aero_risks(self, segments, weather):
        """Cross-references wind vector with track heading to alert for echelons."""
        wind_dir = weather['wind_direction']
        wind_speed = weather['wind_speed']
        alerts = []

        # Sampling logic to detect crosswinds
        for i in range(0, len(segments), 45):
            s = segments[i]
            rel_angle = abs(s['bearing'] - wind_dir) % 360
            if rel_angle > 180: rel_angle = 360 - rel_angle

            # Echelon Alert: Perpendicular wind (70-110 deg) + Speed > 20km/h
            if 70 < rel_angle < 110 and wind_speed > 20:
                dist_at = sum(x['dist'] for x in segments[:i]) / 1000
                alerts.append({
                    "km": round(dist_at, 1),
                    "type": "ECHELON RISK",
                    "detail": f"{round(wind_speed, 1)}km/h Crosswind"
                })
        return alerts[:6]

    def _identify_explosivity_zones(self, segments, surface_type):
        """Identifies steep ramps (Walls for Road, Technical kicks for MTB)."""
        # Threshold: Road muros > 18%, MTB kicks > 22%
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

    def _get_track_weather(self, start_point):
        """Fetches Open-Meteo current weather for the start of the race."""
        try:
            params = {
                "latitude": start_point['lat'],
                "longitude": start_point['lon'],
                "current_weather": "true",
                "windspeed_unit": "kmh"
            }
            res = requests.get(self.weather_api, params=params, timeout=5).json()
            cw = res.get('current_weather', {})
            return {
                "wind_speed": cw.get('windspeed', 0),
                "wind_direction": cw.get('winddirection', 0)
            }
        except:
            return {"wind_speed": 0, "wind_direction": 0}