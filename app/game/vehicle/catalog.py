"""The immutable initial catalog for حاج ممد's car dealership.

Only these predefined models can ever be purchased. Prices live in the
catalog as the initial configuration and are copied to the database's model
rows on first startup; existing database values are not overwritten, so a
future admin/configuration change survives restarts.
"""

from __future__ import annotations

from dataclasses import dataclass

VEHICLE_MODEL_AVAILABLE: str = "available"
VEHICLE_MODEL_UNAVAILABLE: str = "unavailable"
SHOTI_COMPATIBILITY_TAG: str = "shoti"


@dataclass(frozen=True, slots=True)
class VehicleCatalogDefinition:
    """One configurable, predefined dealership model."""

    model_id: int
    code: str
    name: str
    purchase_price: int
    availability_status: str = VEHICLE_MODEL_AVAILABLE
    future_compatibility: tuple[str, ...] = ()

    @property
    def is_shoti_eligible(self) -> bool:
        """Whether a future شوتی service may accept this model."""
        return SHOTI_COMPATIBILITY_TAG in self.future_compatibility


# Keep this order stable: it is the dealership's initial display order.
VEHICLE_CATALOG: tuple[VehicleCatalogDefinition, ...] = (
    VehicleCatalogDefinition(1, "pride_131", "پراید ۱۳۱", 780_000_000),
    VehicleCatalogDefinition(2, "pride_111", "پراید ۱۱۱", 700_000_000),
    VehicleCatalogDefinition(3, "tiba", "تیبا", 1_059_000_000),
    VehicleCatalogDefinition(4, "tiba_2", "تیبا ۲", 1_060_000_000),
    VehicleCatalogDefinition(5, "saina", "ساینا", 1_420_000_000),
    VehicleCatalogDefinition(6, "quick", "کوییک", 1_430_000_000),
    VehicleCatalogDefinition(
        7, "peugeot_405", "پژو ۴۰۵", 1_220_000_000, future_compatibility=(SHOTI_COMPATIBILITY_TAG,)
    ),
    VehicleCatalogDefinition(
        8, "peugeot_pars", "پژو پارس", 1_693_000_000, future_compatibility=(SHOTI_COMPATIBILITY_TAG,)
    ),
    VehicleCatalogDefinition(9, "peugeot_206", "پژو ۲۰۶", 1_200_000_000),
    VehicleCatalogDefinition(10, "peugeot_207", "پژو ۲۰۷", 2_050_000_000),
    VehicleCatalogDefinition(
        11, "samand", "سمند", 1_650_000_000, future_compatibility=(SHOTI_COMPATIBILITY_TAG,)
    ),
    VehicleCatalogDefinition(12, "samand_soren", "سمند سورن", 1_860_000_000),
    VehicleCatalogDefinition(13, "dena", "دنا", 2_460_000_000),
    VehicleCatalogDefinition(14, "dena_plus", "دنا پلاس", 3_375_000_000),
    VehicleCatalogDefinition(15, "rana", "رانا", 1_900_000_000),
    VehicleCatalogDefinition(
        16, "zantia", "زانتیا", 1_200_000_000, future_compatibility=(SHOTI_COMPATIBILITY_TAG,)
    ),
    VehicleCatalogDefinition(17, "l90", "ال۹۰", 1_500_000_000),
    VehicleCatalogDefinition(18, "shahin", "شاهین", 2_200_000_000),
)

CATALOG_BY_ID: dict[int, VehicleCatalogDefinition] = {
    item.model_id: item for item in VEHICLE_CATALOG
}
CATALOG_BY_CODE: dict[str, VehicleCatalogDefinition] = {
    item.code: item for item in VEHICLE_CATALOG
}


def get_catalog_definition(model_id: int) -> VehicleCatalogDefinition | None:
    """Return a fixed definition, never a player-created model."""
    return CATALOG_BY_ID.get(model_id)


def is_supported_model_id(model_id: int) -> bool:
    return model_id in CATALOG_BY_ID
