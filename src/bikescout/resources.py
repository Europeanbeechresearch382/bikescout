from inspect import cleandoc

class BikeScoutResources:
    """Static technical resources for cyclists."""

    SAFETY_CHECKLIST = cleandoc("""
        ### 🛡️ BikeScout Safety Checklist
        1. **M-Check**: Check hubs, bottom bracket, and headset for play.
        2. **Brakes**: Ensure pads have life and levers don't touch the bars.
        3. **Tires**: Check for cuts and ensure correct pressure.
        4. **Chain**: Clean and lubed?
        5. **Emergency**: Do you have a multi-tool, pump, and spare tube?
        6. **Helmet**: Buckle it up!
    """)

    TIRE_PRESSURE_GUIDE = cleandoc("""
        ### 🚲 Tire Pressure Recommendations (Tubeless)
        - **Road (28mm)**: 4.5 - 5.5 Bar (65-80 PSI)
        - **Gravel (40mm)**: 2.0 - 3.0 Bar (30-45 PSI)
        - **MTB (2.3")**: 1.4 - 1.8 Bar (20-26 PSI)

        *Note: Add 0.3 Bar if using inner tubes.*
    """)