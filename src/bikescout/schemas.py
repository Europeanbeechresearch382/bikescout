from pydantic import BaseModel, Field, validator
from typing import Optional, List, Tuple

class RiderProfile(BaseModel):
    weight_kg: float = Field(80.0, description="Rider weight for tire pressure and energy calculations.")
    fitness_level: str = Field("intermediate", description="Fitness level: 'beginner', 'intermediate', 'pro'.")

class BikeSetup(BaseModel):
    bike_type: str = Field("MTB", description="Type: 'MTB', 'Road', 'Gravel', 'E-MTB', 'Enduro'.")
    tire_size: str = Field("29", description="Wheel size: '29', '27.5', '700c', '650b'.")
    is_ebike: bool = Field(False, description="True if the bike has a motor.")
    battery_wh: Optional[int] = Field(None, description="Battery capacity in Wh (required for E-MTB).")

class MissionConstraints(BaseModel):
    radius_km: int = Field(10, description="Target distance for the loop.")
    profile: str = Field("cycling-mountain", description="ORS profile: cycling-mountain, cycling-road, cycling-regular.")
    surface_preference: str = Field("neutral", description="Preferences: 'neutral', 'prefer_paved', 'avoid_unpaved'.")
    complexity: int = Field(3, alias="points", description="Route shape complexity (3-10).")
    seed: int = Field(42, description="Seed for random route generation.")

class RouteGeometry(BaseModel):
    """
    Schema for GeoJSON-style route geometry.
    Coordinates are expected as a list of [longitude, latitude, elevation].
    """
    coordinates: List[List[float]] = Field(
        ...,
        description="A list of points, where each point is [lon, lat, ele].",
        example=[[12.7118, 41.7615, 150.5], [12.7120, 41.7620, 155.2]]
    )

    @validator('coordinates')
    def validate_coordinates_structure(cls, v):
        if not v:
            raise ValueError("Coordinates list cannot be empty.")

        for point in v:
            if len(point) < 2:
                raise ValueError(f"Each point must have at least [lon, lat]. Point found: {point}")
            if len(point) < 3:
                # Se manca l'elevazione, la inizializziamo a 0.0 per evitare crash nel plot
                point.append(0.0)
        return v

    @property
    def has_elevation(self) -> bool:
        """Helper to check if the geometry actually contains vertical data."""
        return any(len(p) > 2 and p[2] != 0 for p in self.coordinates)

    def to_dict(self):
        return {"coordinates": self.coordinates}