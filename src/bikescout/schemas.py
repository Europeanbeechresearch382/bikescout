import uuid
import time
from pathlib import Path
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator

# --- BIKE SCOUT CORE SCHEMAS (PYDANTIC V2) ---

class RiderProfile(BaseModel):
    """
    Physiological data of the user.
    Required fields without defaults to force Agent-User interaction.
    """
    weight_kg: float = Field(
        ...,
        description="Rider weight in kilograms. Critical for tire pressure and energy modeling."
    )
    fitness_level: Literal["beginner", "intermediate", "pro"] = Field(
        ...,
        description="User's athletic preparation level. Affects fatigue and climbing logic."
    )

class BikeSetup(BaseModel):
    """
    Technical configuration of the bicycle.
    Includes cross-validation for electric bike specifications.
    """
    bike_type: Literal["MTB", "Road", "Gravel", "E-MTB", "Enduro"] = Field(
        ...,
        description="The category of the bike, used to filter suitable trail surfaces."
    )
    tire_size: Literal["29", "27.5", "700c", "650b"] = Field(
        ...,
        description="Standard wheel diameter."
    )
    is_ebike: bool = Field(
        False,
        description="Set to True if the bike has an electric motor."
    )
    battery_wh: Optional[int] = Field(
        None,
        description="Battery capacity in Watt-hours. Mandatory if is_ebike is True."
    )

    @model_validator(mode='after')
    def check_ebike_specs(self) -> 'BikeSetup':
        """
        Pydantic V2 model validator.
        Ensures battery data is provided if the bike is electric.
        """
        if self.is_ebike and self.battery_wh is None:
            raise ValueError("battery_wh must be specified for E-MTB setups.")
        return self

class MissionConstraints(BaseModel):
    """
    Tactical constraints for the specific ride/mission.
    """
    radius_km: int = Field(
        ...,
        description="The desired search radius or loop length in kilometers."
    )
    profile: Literal["cycling-mountain", "cycling-road", "cycling-regular"] = Field(
        "cycling-mountain",
        description="The OpenRouteService routing profile."
    )
    surface_preference: Literal["neutral", "prefer_paved", "avoid_unpaved"] = Field(
        "neutral",
        description="User preference for road vs off-road surfaces."
    )
    complexity: int = Field(
        3,
        ge=3,
        le=10,
        serialization_alias="points",
        description="Number of waypoints to generate for the route shape (3-10)."
    )
    seed: int = Field(
        42,
        description="Random seed for reproducibility of generated trails."
    )
    assist_mode: Literal["Eco", "Trail", "Boost"] = Field(
        "Eco",
        description="E-bike motor assistance level. Influences battery range predictions."
    )

class RouteGeometry(BaseModel):
    """
    GeoJSON-compatible geometry container.
    Coordinates format: [longitude, latitude, elevation]
    """
    coordinates: List[List[float]] = Field(
        ...,
        description="A list of coordinate triplets: [lon, lat, ele].",
    )

    @field_validator('coordinates')
    @classmethod
    def validate_coordinates_structure(cls, v: List[List[float]]) -> List[List[float]]:
        """
        Pydantic V2 field validator.
        Ensures each point has [lon, lat] and standardizes elevation.
        """
        if not v:
            raise ValueError("Coordinates list cannot be empty.")

        for point in v:
            if len(point) < 2:
                raise ValueError(f"Invalid point structure: {point}. Expected [lon, lat, ele].")
            if len(point) == 2:
                # Standardize to 3D by adding 0.0 elevation if missing
                point.append(0.0)
        return v

    @property
    def has_elevation(self) -> bool:
        """Helper to verify if the dataset contains meaningful vertical data."""
        return any(len(p) > 2 and p[2] != 0 for p in self.coordinates)

    def to_dict(self):
        """Converts the model back to a standard dictionary for MCP transport."""
        return self.model_dump()