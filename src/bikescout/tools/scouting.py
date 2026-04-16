import requests
import uuid
import time
from pathlib import Path
from bikescout.tools.maps import get_static_map_url
from bikescout.tools.weather import get_weather_forecast
from bikescout.tools.surface import get_surface_analyzer
from bikescout.tools.poi import get_poi_scout
from bikescout.tools.mud import get_mud_risk_analysis
from bikescout.tools.altimetry import get_elevation_profile_image
from bikescout.schemas import RiderProfile, BikeSetup, MissionConstraints, RouteGeometry

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
ORS_BASE_URL = "https://api.openrouteservice.org/v2/directions"

def calculate_detailed_difficulty(dist_km: float, ascent_m: float) -> str:
    """
    Categorizes the route difficulty based on distance, ascent, and average gradient.
    """
    if dist_km == 0:
        return "Unknown"

    # Calculate average gradient
    # Formula: (ascent / (distance * 1000)) * 100
    avg_gradient = (ascent_m / (dist_km * 1000)) * 100

    # 1. EXPERT: High distance, high climbing, or very steep
    if dist_km > 50 or ascent_m > 1000 or avg_gradient > 7:
        return "🔴 Expert (Challenging distance or very steep climbs)"

    # 2. ADVANCED: Significant climbing or moderate distance
    if dist_km > 30 or ascent_m > 600 or avg_gradient > 4:
        return "🟠 Advanced (Requires good fitness and stamina)"

    # 3. MODERATE: Accessible but with some effort
    if dist_km > 15 or ascent_m > 300:
        return "🟡 Moderate (Accessible for regular cyclists)"

    # 4. BEGINNER: Short and flat
    return "🟢 Beginner (Short and relatively flat, ideal for everyone)"

def generate_tactical_gpx(geojson_data, amenities=[]):
    """
    Generates a GPX file with tactical waypoints and optimized track segments.
    Output is saved to ~/.bikescout/gpx/ to avoid Context Window overflow.

    Features:
    - Robust data extraction (handles objects and dicts)
    - Climbing 'WALL' detection (>10% grade) with cooldown
    - Automatic Summit detection
    - Point Decimation (Max 1500 points for device compatibility)
    - Automatic cleanup of files older than 14 days
    """
    try:
        # 1. STORAGE CONFIGURATION & AUTO-CLEANUP
        # Set path to user home directory: ~/.bikescout/gpx/
        home_dir = Path.home() / ".bikescout" / "gpx"
        home_dir.mkdir(parents=True, exist_ok=True)

        # Cleanup: Remove GPX files older than 14 days to save disk space
        now = time.time()
        for f in home_dir.glob("*.gpx"):
            if f.is_file() and (now - f.stat().st_mtime) > (14 * 86400):
                try:
                    f.unlink()
                except:
                    pass # Ignore errors during deletion

        # 2. ROBUST DATA EXTRACTION
        # Handle both RouteGeometry objects (attribute access) and GeoJSON dicts (subscript access)
        if hasattr(geojson_data, 'coordinates'):
            # It's an object (e.g., Pydantic model)
            coords = geojson_data.coordinates
        elif isinstance(geojson_data, dict) and 'features' in geojson_data:
            # It's a standard GeoJSON dictionary
            feature = geojson_data['features'][0]
            coords = feature['geometry']['coordinates']
        else:
            # Fallback: assume the input is the coordinate list itself
            coords = geojson_data

        # 3. OPTIMIZATION: POINT DECIMATION
        # We target a max of 1500 points to ensure compatibility with GPS head units
        MAX_TRACK_POINTS = 1500
        step = max(1, len(coords) // MAX_TRACK_POINTS)
        optimized_coords = coords[::step]

        # 4. XML HEADER CONSTRUCTION
        gpx_xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        gpx_xml += '<gpx version="1.1" creator="BikeScout" xmlns="http://www.topografix.com/GPX/1/1">\n'

        waypoints = ""

        # --- A. WAYPOINT: CYCLING AMENITIES (Water, etc.) ---
        for poi in amenities:
            name = poi.get('name', 'Cycling POI')
            loc = poi.get('location', {})
            p_lat, p_lon = loc.get('lat'), loc.get('lon')

            if p_lat and p_lon:
                waypoints += f'  <wpt lat="{p_lat}" lon="{p_lon}">\n'
                waypoints += f'    <name>{name}</name>\n'
                waypoints += f'    <sym>Watering Hole</sym>\n'
                waypoints += f'  </wpt>\n'

        # --- B. WAYPOINT: SUMMIT DETECTION ---
        # coordinates format: [longitude, latitude, elevation]
        if coords and len(coords[0]) > 2:
            peak = max(coords, key=lambda x: x[2])
            waypoints += f'  <wpt lat="{peak[1]}" lon="{peak[0]}">\n'
            waypoints += f'    <name>SUMMIT: {int(peak[2])}m</name>\n'
            waypoints += f'    <sym>Summit</sym>\n'
            waypoints += f'  </wpt>\n'

        # --- C. WAYPOINT: STEEP CLIMBS (COOLDOWN LOGIC) ---
        # Detects sections over 10% grade. Uses cooldown to avoid waypoint clutter.
        last_wall_index = -50
        for i in range(5, len(coords) - 10, 10):
            # Cooldown check: Skip if a 'WALL' was placed in the last 40 points
            if i < last_wall_index + 40:
                continue

            p1, p2 = coords[i], coords[i+10]

            # Fast distance approximation in meters
            d_lat = (p2[1] - p1[1]) * 111139
            d_lon = (p2[0] - p1[0]) * 111139 * 0.7
            dist = (d_lat**2 + d_lon**2)**0.5

            if dist > 60:
                grade = ((p2[2] - p1[2]) / dist) * 100
                if grade > 10:
                    waypoints += f'  <wpt lat="{p1[1]}" lon="{p1[0]}">\n'
                    waypoints += f'    <name>WALL: {int(grade)}%</name>\n'
                    waypoints += f'    <sym>Danger Area</sym>\n'
                    waypoints += f'  </wpt>\n'
                    last_wall_index = i

        # --- D. TRACK CONSTRUCTION ---
        track = '  <trk>\n    <name>BikeScout Tactical Route</name>\n    <trkseg>\n'
        for lon, lat, ele in optimized_coords:
            track += f'      <trkpt lat="{lat}" lon="{lon}"><ele>{ele}</ele></trkpt>\n'
        track += '    </trkseg>\n  </trk>\n'

        # 5. FILE PERSISTENCE
        full_content = gpx_xml + waypoints + track + '</gpx>'
        filename = f"tactical_route_{uuid.uuid4().hex[:6]}.gpx"
        file_path = home_dir / filename

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(full_content)

        # 6. RETURN LIGHTWEIGHT RESPONSE
        # Returning the path instead of the full XML string prevents Context Window crashes
        return {
            "status": "Success",
            "message": "Tactical GPX file successfully exported.",
            "file_location": str(file_path),
            "tactical_stats": {
                "total_points": len(coords),
                "optimized_points": len(optimized_coords),
                "waypoints_count": waypoints.count('<wpt')
            },
            "instructions": f"The file is safe in your home directory: {file_path}"
        }

    except Exception as e:
        return {
            "status": "Error",
            "message": f"GPX Generation failed: {str(e)}"
        }

def get_complete_trail_scout(
        api_key,
        lat: float,
        lon: float,
        rider: RiderProfile,
        bike: BikeSetup,
        mission: MissionConstraints,
        include_gpx: bool = True,
        include_map: bool = False,
        output_level: str = "standard"  # "summary" | "standard" | "full"
):
    """
    The Master Orchestrator: Finds a specific trail and enriches it with
    Surface Analysis, Weather, Cycling POIs, and Mud Risk.

    """
    # --- 1. CONFIGURATION & HEADERS ---
    headers = {
        'Accept': 'application/json, application/geo+json',
        'Authorization': api_key,
        'Content-Type': 'application/json'
    }

    routing_payload = {
        "coordinates": [[lon, lat]],
        "options": {"round_trip": {"length": mission.radius_km * 1000, "seed": 42}},
        "elevation": "true",
        "extra_info": ["surface", "steepness"]
    }

    try:
        # --- 2. EXECUTE PRIMARY ROUTING ---
        endpoint = f"{ORS_BASE_URL}/{mission.profile}/geojson"
        response = requests.post(endpoint, json=routing_payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        feature = data['features'][0]
        props = feature['properties']
        summary = props.get('summary', {})
        route_geo = RouteGeometry(coordinates=feature['geometry']['coordinates'])

        dist_km = round(summary.get('distance', 0) / 1000, 2)
        ascent_m = round(props.get('ascent', 0), 0)

        # Extract dominant surface
        raw_surface_extras = props.get('extras', {}).get('surface', {}).get('summary', [])
        dominant_id = raw_surface_extras[0]['value'] if raw_surface_extras else 10
        dominant_surface_name = _map_surface_id(dominant_id)

        # --- 3. CALL: SURFACE ANALYZER ---
        # Only perform deep surface analysis if level is not summary
        surface_report = {}
        if output_level != "summary":
            try:
                surface_report = get_surface_analyzer(api_key, lat, lon, rider, bike, mission)
            except Exception as e:
                surface_report = {"status": "Error", "message": str(e)}

        # --- 4. CALL: WEATHER & MUD ---
        weather_report = get_weather_forecast(lat, lon)
        mud_analysis = get_mud_risk_analysis(lat, lon, dominant_surface_name)

        # --- 5. CALL: POI SCOUT (Logistics) ---
        amenities = []
        if output_level == "full":
            try:
                poi_res = get_poi_scout(api_key, lat, lon, mission.radius_km)
                amenities = poi_res.get('amenities', []) if poi_res.get('status') == "Success" else []
            except:
                amenities = []

        # --- 6. FINAL CONSOLIDATED RESPONSE CONSTRUCTION ---

        # Build Tactical Briefing (Shared across levels)
        tactical_info = {
            "distance_km": dist_km,
            "ascent_m": ascent_m,
            "difficulty": calculate_detailed_difficulty(dist_km, ascent_m),
        }

        # Add Surface Analysis if requested
        if output_level != "summary":
            tactical_info["surface_analysis"] = surface_report

        response_payload = {
            "status": "Success",
            "info": tactical_info,
            "conditions": {
                "weather": weather_report.get('next_4_hours', []) if isinstance(weather_report, dict) else [],
                "mud_risk": mud_analysis,
                "safety_advice": weather_report.get('safety_advice', "") if isinstance(weather_report, dict) else ""
            }
        }

        # Include logistics only in Full or Standard
        if output_level != "summary":
            response_payload["logistics"] = {
                "nearby_amenities": amenities[:5] if amenities else "Available in Full report"
            }

        # Static Map: Generate only if requested to save header space / processing
        if include_map:
            response_payload["map_image_url"] = get_static_map_url(data)

        # GPX Content: Generate only if requested (heaviest part)
        if include_gpx:
            try:
                gpx_report = generate_tactical_gpx(
                    geojson_data=route_geo,
                    amenities=nearby_pois if 'nearby_pois' in locals() else []
                )
                if gpx_report["status"] == "Success":
                    response_payload["gpx_export_path"] = gpx_report["file_location"]
                    response_payload["gpx_stats"] = gpx_report.get("tactical_stats")
                else:
                    response_payload["gpx_error"] = gpx_report.get("message")

            except Exception as e:
                response_payload["gpx_error"] = f"GPX generation failed: {str(e)}"

        # Elevation Profile
        if output_level != "summary":
            try:
                altimetry_report = get_elevation_profile_image(geometry=route_geo)

                if altimetry_report["status"] == "Success":
                    response_payload["elevation_profile_path"] = altimetry_report["file_location"]

                response_payload["elevation_summary"] = altimetry_report.get("summary", "")

            except Exception as e:
                response_payload["elevation_profile_error"] = f"Main call failed: {str(e)}"

        return response_payload

    except Exception as e:
        return {"status": "Error", "message": f"Master Orchestrator failed: {str(e)}"}

def _map_surface_id(s_id):
    """Internal helper to convert ORS surface IDs to strings for Mud Analysis."""
    mapping = {1: "asphalt", 2: "unpaved", 5: "gravel", 10: "dirt", 11: "grass", 12: "compact"}
    return mapping.get(s_id, "dirt")