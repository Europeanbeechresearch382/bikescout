import requests

def get_surface_analyzer(api_key: str, lat: float, lon: float, radius_km: int, profile: str, bike_type: str, tire_width_mm: int):
    """
    Analyzes the route surface composition and bike compatibility.
    Includes fallback mechanisms for both profiles and metadata availability.
    """

    attempts = [
        (profile, ["surface", "waytype", "tracktype"]),
        (profile, ["surface", "waytype"]), # Fallback
        ("cycling-regular", ["surface", "waytype"]) # Fallback extreme!
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

                if "extra_info" in msg or "tracktype" in msg:
                    last_error = f"Metadata '{current_extras}' not supported for {current_profile}."
                    continue
                last_error = msg
                continue

            response.raise_for_status()
            data = response.json()

            surface_map = {
                0: "Unknown", 1: "Asphalt", 2: "Unpaved", 3: "Paved", 4: "Cobblestone",
                5: "Gravel", 6: "Fine Gravel", 7: "Atv", 8: "Pebbles", 9: "Wood",
                10: "Stepping Stones", 11: "Grass", 12: "Compact", 13: "Sett", 14: "Concrete"
            }
            tracktype_map = {21: "Grade 1", 22: "Grade 2", 23: "Grade 3", 24: "Grade 4", 25: "Grade 5"}

            extras = data['features'][0]['properties']['extras']
            breakdown = []
            warnings = []
            is_compatible = True

            if 'surface' in extras:
                for item in extras['surface']['summary']:
                    name = surface_map.get(item['value'], "Other")
                    percentage = round(item['amount'], 1)
                    if (bike_type.lower() == "road" or tire_width_mm < 30) and \
                       name in ["Gravel", "Unpaved", "Pebbles", "Grass", "Other", "Fine Gravel"]:
                        is_compatible = False
                        warnings.append(f"High risk: {percentage}% is {name}.")
                    breakdown.append({"type": name, "percentage": f"{percentage}%"})

            if 'tracktype' in extras:
                for item in extras['tracktype']['summary']:
                    grade_val = item['value']
                    grade_name = tracktype_map.get(grade_val, "Unknown")
                    if bike_type.lower() == "gravel" and grade_val >= 24:
                        warnings.append(f"Technical: contains {grade_name} sections.")

            return {
                "status": "Success",
                "profile_used": current_profile,
                "metadata_retrieved": current_extras,
                "bike_setup_check": {
                    "compatible": is_compatible,
                    "bike_used": bike_type,
                    "tire_width": f"{tire_width_mm}mm"
                },
                "surface_breakdown": breakdown,
                "safety_warnings": warnings,
                "total_distance_m": data['features'][0]['properties']['summary']['distance']
            }

        except Exception as e:
            last_error = str(e)
            continue

    return {
        "status": "Error",
        "message": f"Route analysis failed. Details: {last_error}",
        "hint": "The requested area might not support technical trail metadata."
    }