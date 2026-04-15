# Why BikeScout? (vs Generic Maps)

While Google Maps or standard navigation tools are excellent for urban commuting, they fail when the terrain gets technical. **BikeScout** bridges the gap between a simple "line on a map" and the technical reality of professional cycling, turning your AI into an expert local guide.

## Truth in Elevation (Progressive Filtering)
Raw satellite data (SRTM) often suffers from "noise," overestimating total vertical gain by up to 40% in mountainous areas due to sudden spikes in readings.
* **Generic Maps:** Display "jagged" elevation profiles that inflate effort and make charts unreadable.
* **BikeScout:** Uses a **Progressive Elevation Filter**. Our algorithm recognizes and smooths out satellite sensor errors, returning a total ascent value that matches real-world barometric sensors (Garmin/Wahoo).

## Beyond "Paved" vs "Unpaved" (S-Scale Grading)
For a standard navigator, a trail is just a trail. For a cyclist, the difference between packed gravel and a bed of loose rocks is the difference between fun and danger.
* **Generic Maps:** Indiscriminately label everything that isn't asphalt as "unpaved."
* **BikeScout:** Parses deep OpenStreetMap metadata to extract the **MTB-Scale (S0-S5)** and **SAC-Scale**. It warns you if you'll encounter a Grade S0 (easy) or an S3 (technical with rocks and steps), allowing you to decide if your setup is appropriate.

## Beyond traditional POI
Generic maps often prioritize sponsored results or restaurants. BikeScout probes deep OpenStreetMap tags like amenity=drinking_water and shop=bicycle. These points are often verified by the cycling community, ensuring you find a working fountain on a mountain pass rather than a closed supermarket.

## Historical Weather data
Standard forecasts only tell you if it will rain. BikeScout analyzes what has already happened. Since clay-heavy soil can remain unrideable for days after a storm while sandy soil dries in hours, this tool provides the specific context needed for off-road decision making.

## Discipline-Specific Intelligence
Effort is relative to your gear. 500m of climbing feels different on a 7kg Road bike than on a 16kg Enduro rig with 2.4" knobby tires.
* **Generic Maps:** Provide "standard" travel times and difficulty based on generic averages.
* **BikeScout:** Features a **Dynamic Effort Engine**. It calculates difficulty and climb categorization (from Cat 4 to *Hors Catégorie*) based specifically on your **Bike Type** (Road, Gravel, MTB, Enduro) and your **Tire Setup**.

## Native AI Orchestration (MCP)
BikeScout isn't just an isolated script; it's a native extension for next-generation large language models.
* **Generic Maps:** Require manual searches, screenshots, and visual interpretation by the user.
* **BikeScout:** Is a **Model Context Protocol (MCP)** server. It allows Claude, Cursor, or other LLMs to "reason" like a local guide, automatically cross-referencing weather, soil type, and technical setup in a single conversational flow.

## Comparison at a Glance

| Feature | Generic Maps | BikeScout AI |
| :--- | :--- | :--- |
| **Elevation Gain** | Raw & Noisy | **Filtered & Realistic** |
| **Surface Analysis** | Basic (Paved/Dirt) | **Technical (S-Scale/Tracktype)** |
| **Difficulty Rating** | Time-based only | **Weighted by Bike Type** |
| **Climb Grading** | None | **UCI-Standard (Cat 4 to HC)** |
| **Safety Logistics** | General Stores/Gas | **Cycling POIs (Water/Repair/Shelter)** |
| **Condition Predictive** | Future Weather only | **Mud Risk (72h Rain + Soil Analysis)** |
| **AI Integration** | Manual / External | **Native MCP Tooling** |