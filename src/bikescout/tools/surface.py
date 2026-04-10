import requests

def get_surface_analyzer(api_key: str, lat: float, lon: float, radius_km: int, profile: str, bike_type: str, tire_width_mm: int):
    """
    Analyzes the route surface composition, bike compatibility, and climb difficulty.
    Implements fallback mechanisms for profiles and metadata (extra_info) availability.
    """

    # Attempts: (profile, extra_info_list)
    # We try full metadata first, then downgrade if the API rejects specific tags like 'tracktype'
    attempts = [
        (profile, ["surface", "waytype", "tracktype"]),
        (profile, ["surface", "waytype"]),
        ("cycling-regular", ["surface", "waytype"])
    ]

    last_error = ""

    for current_profile, current_extras in attempts:
        url = f"https://api.openrouteservice.org/v2/directions/{current_profile}/geojson"

        headers = {
            'Accept': 'application/json, application/geo+json, application/gpx+xml, img/png; charset=utf-8',
            'Authorization': api_key,
            'Content-Type': 'application/json; charset=utf-8'
        }

        body = {
            "coordinates": [[lon, lat]],
            "elevation": True,
            "options": {
                "round_trip": {
                    "length": radius_km * 1000,
                    "points": 3,
                    "seed": 42
                }
            },
            "extra_info": current_extras
        }

        try:
            response = requests.post(url, json=body, headers=headers)

            if response.status_code == 400:
                error_data = response.json()
                msg = error_data.get('error', {}).get('message', '')

                # If the error is about unsupported metadata, move to the next fallback attempt
                if "extra_info" in msg or "tracktype" in msg:
                    last_error = f"Metadata '{current_extras}' not supported for {current_profile}."
                    continue
                last_error = msg
                continue

            response.raise_for_status()
            data = response.json()

            # Technical mappings for ORS attributes
            surface_map = {
                0: "Unknown", 1: "Asphalt", 2: "Unpaved", 3: "Paved", 4: "Cobblestone",
                5: "Gravel", 6: "Fine Gravel", 7: "Atv", 8: "Pebbles", 9: "Wood",
                10: "Stepping Stones", 11: "Grass", 12: "Compact", 13: "Sett", 14: "Concrete"
            }
            tracktype_map = {21: "Grade 1", 22: "Grade 2", 23: "Grade 3", 24: "Grade 4", 25: "Grade 5"}

            # Extraction of general route metrics
            properties = data['features'][0]['properties']
            summary = properties['summary']
            total_dist_m = summary['distance']
            total_ascent = properties.get('ascent', 0)

            # --- ENHANCED MTB/ROAD CLIMB LOGIC ---

            # 1. Base Gradient Calculation
            avg_gradient = (total_ascent / (total_dist_m / 2)) * 100 if total_dist_m > 0 else 0

            # 2. Effort Multiplier: MTB trails are ~30-50% harder than asphalt for the same gradient
            effort_multiplier = 1.3 if "mountain" in current_profile else 1.0

            # 3. Adjusted Score
            # We multiply the ascent by the effort and the steepness
            adjusted_score = total_ascent * (avg_gradient / 10) * effort_multiplier

            climb_category = "Flat / Rolling"

            if total_ascent >= 50: # Lower threshold for MTB
                if adjusted_score >= 800 or total_ascent > 1000:
                    climb_category = "Hors Catégorie (HC) - Extreme MTB Epic"
                elif adjusted_score >= 500 or total_ascent > 600:
                    climb_category = "Category 1 - Brutal Ascent"
                elif adjusted_score >= 300 or total_ascent > 400:
                    climb_category = "Category 2 - Tough Climb"
                elif adjusted_score >= 150 or total_ascent > 200:
                    climb_category = "Category 3 - Challenging"
                else:
                    climb_category = "Category 4 - Short Burner"

            # --- SURFACE & COMPATIBILITY ANALYSIS ---
            extras = properties.get('extras', {})
            breakdown = []
            warnings = []
            is_compatible = True

            if 'surface' in extras:
                for item in extras['surface']['summary']:
                    name = surface_map.get(item['value'], "Other")
                    percentage = round(item['amount'], 1)

                    if bike_type.lower() != "mtb" and (bike_type.lower() == "road" or tire_width_mm < 30):
                        if name in ["Gravel", "Unpaved", "Pebbles", "Grass", "Other", "Fine Gravel"]:
                            is_compatible = False
                            warnings.append(f"High risk: {percentage}% of the route is {name}.")

                    breakdown.append({"type": name, "percentage": f"{percentage}%"})

            if 'tracktype' in extras:
                for item in extras['tracktype']['summary']:
                    grade_val = item['value']
                    grade_name = tracktype_map.get(grade_val, "Unknown")
                    # Rule: Gravel bikes should avoid Grade 4 (soft/unpaved) or Grade 5 (very difficult)
                    if bike_type.lower() == "gravel" and grade_val >= 24:
                        warnings.append(f"Technical Warning: Includes {grade_name} sections (rough/soft terrain).")

            return {
                "status": "Success",
                "profile_used": current_profile,
                "technical_summary": {
                    "distance_km": round(total_dist_m / 1000, 2),
                    "elevation_gain_m": round(total_ascent, 0),
                    "climb_category": climb_category,
                    "est_avg_climb_gradient": f"{round(avg_gradient, 1)}%"
                },
                "bike_setup_check": {
                    "compatible": is_compatible,
                    "bike_used": bike_type,
                    "tire_width": f"{tire_width_mm}mm"
                },
                "surface_breakdown": breakdown,
                "safety_warnings": warnings
            }

        except Exception as e:
            last_error = str(e)
            continue

    # Final error response if all fallbacks fail
    return {
        "status": "Error",
        "message": f"Route analysis failed. Details: {last_error}",
        "hint": "The area might lack mapped trails, or the starting point is too far from a road."
    }