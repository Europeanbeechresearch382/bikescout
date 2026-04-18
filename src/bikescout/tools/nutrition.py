def get_nutrition_plan(duration_hours: float, temp_c: float, intensity_score: int):
    """
    Core logic for sweat rate and glycogen depletion prediction.
    """
    # Hydration Logic: Base 500ml/hr + 100ml for every 5°C above 20°C
    base_rate = 500
    heat_adjustment = max(0, (temp_c - 20) // 5) * 100

    # Intensity multiplier (Scaling from 0.9 to 1.5)
    intensity_mult = 0.9 + (intensity_score / 200)

    hourly_fluid = (base_rate + heat_adjustment) * intensity_mult
    total_fluid = (hourly_fluid * duration_hours) / 1000 # Convert to Liters

    # Nutrition Logic: 30-90g Carbs based on intensity
    if intensity_score > 70:
        carb_rate = 80  # High intensity (HC/Cat 1)
        intensity_label = "High"
    elif intensity_score > 40:
        carb_rate = 60  # Moderate
        intensity_label = "Moderate"
    else:
        carb_rate = 40  # Low (Z2/Flat)
        intensity_label = "Low"

    total_carbs = carb_rate * duration_hours

    # Tactical Alerts
    alerts = []
    if temp_c > 28 or duration_hours > 3:
        alerts.append("ELECTROLYTE CRITICAL: High sweat rate or duration detected. Add sodium to bottles.")
    if carb_rate >= 80:
        alerts.append("FUELING ALERT: High intensity detected. Train your gut for 80g+/hr intake.")

    return {
        "status": "Success",
        "mission_nutrition_briefing": {
            "fluids": {
                "total_liters": round(total_fluid, 1),
                "hourly_rate_ml": round(hourly_fluid)
            },
            "carbohydrates": {
                "total_grams": round(total_carbs),
                "hourly_target_g": carb_rate,
                "intensity_context": intensity_label
            },
            "tactical_advice": alerts
        }
    }