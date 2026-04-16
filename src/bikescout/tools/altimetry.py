import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import io
import base64
import uuid
import time
from pathlib import Path
from bikescout.schemas import RouteGeometry

def _generate_altimetry_plot(geometry: list, width: int = 8, height: int = 3):
    """
    Generates a elevation profile plot with gradient coding.
    Returns a base64 encoded PNG string.
    """
    if not geometry or len(geometry) < 2:
        return None

    # --- 1. Data Extraction ---
    # geometry is [[lon, lat, ele], [lon, lat, ele], ...]
    elevations = [p[2] for p in geometry]

    # Calculate cumulative distance along the path (X-axis)
    # Reuse existing haversine if available, otherwise use np.linalg.norm for simplification here
    distances = [0]
    total_dist = 0
    for i in range(len(geometry) - 1):
        p1 = geometry[i]
        p2 = geometry[i+1]
        # Simplistic distance for plot (not geodesic accurate, but fine for profile shape)
        # Use existing haversine_distance function for better results if imported
        d = np.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2) * 111000 # Rough meter conversion
        total_dist += d
        distances.append(total_dist)

    dist_km = [d / 1000 for d in distances]

    # --- 2. Calculate Gradients for Color Coding ---
    grades = []
    for i in range(len(elevations) - 1):
        rise = elevations[i+1] - elevations[i]
        run = distances[i+1] - distances[i]
        if run > 0:
            grades.append((rise / run) * 100) # Percentage gradient
        else:
            grades.append(0)
    grades.append(0) # Pad last point

    # --- 3. Setup Plot ---
    plt.figure(figsize=(width, height), dpi=100)
    ax = plt.gca()

    # Define the custom color map (Green <3%, Yellow 4-7%, Red >8%)
    cmap = mcolors.LinearSegmentedColormap.from_list("grav_cmap", ["#2ecc71", "#f1c40f", "#e74c3c"])
    norm = mcolors.Normalize(vmin=0, vmax=10) # Normalize 0% to 10% grade

    # --- 4. Draw the Profile with Gradient Coding (PolyCollection) ---
    # To color code segments, we draw the fill as multiple vertical segments
    for i in range(len(dist_km) - 1):
        x = [dist_km[i], dist_km[i+1]]
        y = [elevations[i], elevations[i+1]]

        # Color based on average grade of the segment
        avg_grade = abs(grades[i]) # Focus on steepness, ignore direction for color here
        color = cmap(norm(avg_grade))

        plt.fill_between(x, y, min(elevations) - 10, color=color, alpha=0.8)

    # Add the top border line
    plt.plot(dist_km, elevations, color='#7f8c8d', linewidth=1.5, alpha=0.9)

    # --- 5. Styling & Cleanliness (Tactical Briefing Style) ---
    ax.set_facecolor('#ffffff') # White background
    plt.title("Visual Altimetry Profile (Vertical Effort)", fontsize=12, fontweight='bold', color='#2c3e50')
    plt.xlabel("Distance (km)", fontsize=10, color='#34495e')
    plt.ylabel("Elevation (m)", fontsize=10, color='#34495e')

    plt.grid(True, which='both', linestyle='--', linewidth=0.5, color='#bdc3c7', alpha=0.5)
    plt.tight_layout()

    # --- 6. Encode to Base64 ---
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0.1)
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close() # Important to free memory

    return img_base64

def get_elevation_profile_image(geometry: RouteGeometry, width: int = 8, height: int = 3):
    """
    Generates an elevation profile, saves it to ~/.bikescout/altimetry/
    and performs auto-cleaning of old files.
    """
    try:
        coords_list = geometry.coordinates

        home_dir = Path.home() / ".bikescout" / "altimetry"
        home_dir.mkdir(parents=True, exist_ok=True)

        now = time.time()
        for f in home_dir.glob("*.png"):
            if f.is_file() and (now - f.stat().st_mtime) > (3 * 86400): # 3 days
                try:
                    f.unlink()
                except: pass

        plot_result = _generate_altimetry_plot(coords_list, width, height)

        raw_data = plot_result.get("image_data_url") if isinstance(plot_result, dict) else plot_result
        if "base64," in raw_data:
            raw_data = raw_data.split("base64,")[1]

        if not raw_data:
            return {"status": "Error", "message": "No plot data."}

        filename = f"bs_altimetry_{uuid.uuid4().hex[:6]}.png"
        file_path = home_dir / filename

        with open(file_path, "wb") as f:
            f.write(base64.b64decode(raw_data))

        return {
            "status": "Success",
            "message": "Elevation profile stored in BikeScout home directory.",
            "file_location": str(file_path),
            "summary": "Visual sparkline generated and cached.",
            "instructions": f"The file is safe in your home directory: {file_path}"
        }

    except Exception as e:
        return {"status": "Error", "message": f"Altimetry home-storage failed: {str(e)}"}