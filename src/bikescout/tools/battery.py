def calculate_battery_drain(battery_wh, assist_level, weight_kg, ascent_m, distance_km, surface_breakdown, mud_index):
    """
    Predicts E-MTB battery consumption using physics-based modeling.
    Handles surface friction, gravitational work, and mud drag.
    """
    # 1. Input Sanitization
    # Ensures surface_breakdown is iterable as (key, value) regardless of type (dict or list of tuples)
    if isinstance(surface_breakdown, dict):
        surface_items = surface_breakdown.items()
    elif isinstance(surface_breakdown, list):
        surface_items = surface_breakdown
    else:
        surface_items = []

    # 2. Base Energy Consumption (Horizontal work)
    # Average E-MTB motor efficiency scaling based on assistance level
    assist_multipliers = {"Eco": 1.0, "Trail": 1.5, "Boost": 2.2}
    multiplier = assist_multipliers.get(assist_level, 1.5)

    # Base rate: ~12 Wh/km (standard for modern mid-drive motors in Eco)
    base_rate_wh_km = 12 * multiplier
    energy_flat = (distance_km * base_rate_wh_km)

    # 3. Potential Energy (Vertical work: Mass * Gravity * Height)
    # Efficiency factor (~75%) accounts for motor, drivetrain, and heat loss
    # Formula: (kg * 9.81 * m) / (efficiency * seconds_in_hour)
    energy_climb = (weight_kg * 9.81 * ascent_m) / (0.75 * 3600)

    # 4. Rolling Resistance (Surface Penalty)
    # Different surfaces require more torque/energy to maintain speed
    surface_penalty = 0
    for item in surface_items:
        try:
            # Handle both dictionary items and list of tuples/lists
            surf, pct = item if isinstance(item, (list, tuple)) else (item, surface_breakdown[item])

            coef = 1.0
            if surf in ["Gravel", "Fine Gravel", "Compact"]:
                coef = 1.15
            elif surf in ["Unpaved", "Grass", "Cobblestone", "Dirt"]:
                coef = 1.35
            elif surf in ["Sand", "Deep Mud"]:
                coef = 1.6

            # Apply penalty to the horizontal component based on the percentage of that surface
            surface_penalty += (energy_flat * (float(pct) / 100) * (coef - 1))
        except (ValueError, TypeError, KeyError):
            continue # Skip malformed surface data

    # 5. Mud Suction (TAEL Model Integration)
    # Mud increases drain via drivetrain friction and tire 'stickiness'
    mud_penalty = (energy_flat * 0.4) * mud_index

    total_wh_spent = energy_flat + energy_climb + surface_penalty + mud_penalty

    # 6. Battery SoC (State of Charge) Calculation
    remaining_wh = max(0, battery_wh - total_wh_spent)
    remaining_pct = round((remaining_wh / battery_wh) * 100, 1)

    # 7. Safety Buffer logic
    status = "SAFE"
    if remaining_pct < 15:
        status = "CRITICAL"
    elif remaining_pct < 25:
        status = "WARNING"

    return {
        "estimated_drain_wh": round(total_wh_spent, 1),
        "remaining_battery_pct": remaining_pct,
        "safety_buffer_status": status,
        "breakdown_wh": {
            "horizontal_base": round(energy_flat, 1),
            "vertical_climb": round(energy_climb, 1),
            "terrain_friction": round(surface_penalty + mud_penalty, 1)
        }
    }