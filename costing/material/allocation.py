"""
Material Cost Allocation Module.

Allocates sheet material cost to individual parts based on:
- Occupied area (recommended): outer contour without holes
- Legacy utilization factor: divides by utilization ratio

Sheet modes:
- FIXED_SHEET: Standard sheet format (e.g., 1500x3000)
- CUT_TO_LENGTH: Sheet trimmed to actual usage in Y axis
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


# PROGI DECYZYJNE
FULL_SHEET_THRESHOLD = 0.94  # Jesli maxY >= 94% dlugosci arkusza, uzyj pelny arkusz


class SheetMode(Enum):
    """Sheet sizing mode."""
    FIXED_SHEET = "FIXED_SHEET"          # Standard sheet format
    CUT_TO_LENGTH = "CUT_TO_LENGTH"      # Trimmed to actual usage


class AllocationModel(Enum):
    """Cost allocation model."""
    OCCUPIED_AREA = "OCCUPIED_AREA"      # Allocate by outer contour area
    UTILIZATION_FACTOR = "UTILIZATION_FACTOR"  # Legacy: divide by utilization


@dataclass
class SheetSpec:
    """Sheet specification."""
    width_mm: float                       # Sheet width [mm]
    length_mm_nominal: float              # Nominal length [mm] (FIXED_SHEET)
    used_length_y_mm: Optional[float] = None  # Actual used length [mm] (CUT_TO_LENGTH)
    trim_margin_y_mm: float = 10.0        # Safety margin for trimming [mm]
    mode: SheetMode = SheetMode.FIXED_SHEET

    @property
    def area_used_mm2(self) -> float:
        """
        Calculate actual sheet area used.

        REGULA 94%:
        Jesli uzyta dlugosc (maxY z nestingu) >= 94% dlugosci nominalnej arkusza,
        traktujemy arkusz jako pelny - pozostaly pasek jest za maly do dalszego
        wykorzystania i zostanie zlomowany.

        Returns:
            Powierzchnia uzyta [mm2]
        """
        if self.mode == SheetMode.CUT_TO_LENGTH and self.used_length_y_mm is not None:
            # Sprawdz regule 94%
            utilization_ratio = self.used_length_y_mm / self.length_mm_nominal
            if utilization_ratio >= FULL_SHEET_THRESHOLD:
                # Uzyj pelny arkusz - pozostaly pasek zbyt maly
                return self.width_mm * self.length_mm_nominal
            # Standardowy tryb CUT_TO_LENGTH
            return self.width_mm * (self.used_length_y_mm + self.trim_margin_y_mm)
        return self.width_mm * self.length_mm_nominal

    def should_use_full_sheet(self) -> bool:
        """
        Sprawdz czy nalezy uzyc pelnego arkusza (regula 94%).

        Returns:
            True jesli maxY >= 94% dlugosci nominalnej
        """
        if self.used_length_y_mm is None:
            return True  # Brak danych - zakładamy pelny arkusz
        return (self.used_length_y_mm / self.length_mm_nominal) >= FULL_SHEET_THRESHOLD

    @property
    def area_used_m2(self) -> float:
        """Area in square meters."""
        return self.area_used_mm2 / 1_000_000


@dataclass
class MaterialSpec:
    """Material specification for cost calculation."""
    material_id: str
    thickness_mm: float
    density_kg_m3: float = 7850.0         # Default: steel
    price_pln_per_kg: Optional[float] = None
    price_pln_per_m2: Optional[float] = None

    def calculate_sheet_cost(self, sheet: SheetSpec) -> float:
        """Calculate cost for a sheet of this material."""
        area_m2 = sheet.area_used_m2
        thickness_m = self.thickness_mm / 1000.0

        if self.price_pln_per_m2 is not None:
            return area_m2 * self.price_pln_per_m2

        if self.price_pln_per_kg is not None:
            mass_kg = area_m2 * thickness_m * self.density_kg_m3
            return mass_kg * self.price_pln_per_kg

        raise ValueError("Either price_pln_per_kg or price_pln_per_m2 must be set")


@dataclass
class PartPlacement:
    """Part placement on a sheet."""
    part_id: str
    instance_id: str
    occupied_area_mm2: float              # Outer contour area (no holes subtracted)
    net_area_mm2: float = 0.0             # Net area (with holes subtracted)
    qty_in_sheet: int = 1


def calculate_sheet_utilization(parts: List[PartPlacement], sheet: SheetSpec) -> float:
    """
    Calculate sheet utilization (ratio of occupied area to sheet area).

    Args:
        parts: List of part placements on sheet
        sheet: Sheet specification

    Returns:
        Utilization ratio (0-1)
    """
    total_occupied = sum(p.occupied_area_mm2 * p.qty_in_sheet for p in parts)
    return total_occupied / sheet.area_used_mm2 if sheet.area_used_mm2 > 0 else 0.0


def allocate_material_cost_occupied_area(
    sheet_cost_pln: float,
    parts: List[PartPlacement]
) -> Dict[str, float]:
    """
    Allocate material cost to parts based on occupied area (RECOMMENDED).

    Formula: part_cost = sheet_cost * (occupied_area_part / Σ occupied_area_parts)

    This method:
    - Fairly distributes cost based on how much sheet space each part uses
    - Parts with holes don't get artificially cheaper prices
    - Reflects true "sheet occupation" for nesting purposes

    Args:
        sheet_cost_pln: Total sheet cost [PLN]
        parts: List of part placements

    Returns:
        Dict mapping instance_id to material cost [PLN]
    """
    costs = {}

    total_occupied = sum(p.occupied_area_mm2 * p.qty_in_sheet for p in parts)

    if total_occupied <= 0:
        return {p.instance_id: 0.0 for p in parts}

    for part in parts:
        part_share = (part.occupied_area_mm2 * part.qty_in_sheet) / total_occupied
        costs[part.instance_id] = sheet_cost_pln * part_share

    return costs


def allocate_material_cost_utilization(
    sheet_cost_pln: float,
    sheet: SheetSpec,
    parts: List[PartPlacement],
    utilization: Optional[float] = None
) -> Dict[str, float]:
    """
    Allocate material cost using utilization factor (LEGACY).

    Formula: part_cost = (occupied_area * (sheet_cost / sheet_area)) / utilization

    This method adjusts for utilization - lower utilization means higher
    per-part cost to account for wasted material.

    Args:
        sheet_cost_pln: Total sheet cost [PLN]
        sheet: Sheet specification
        parts: List of part placements
        utilization: Pre-calculated utilization (if None, calculated from parts)

    Returns:
        Dict mapping instance_id to material cost [PLN]
    """
    costs = {}

    if utilization is None:
        utilization = calculate_sheet_utilization(parts, sheet)

    if utilization <= 0:
        utilization = 0.01  # Minimum 1% to avoid division by zero

    cost_per_mm2 = sheet_cost_pln / sheet.area_used_mm2 if sheet.area_used_mm2 > 0 else 0

    for part in parts:
        base_cost = part.occupied_area_mm2 * cost_per_mm2
        # Divide by utilization to increase cost for low-utilization sheets
        part_cost = base_cost / utilization
        costs[part.instance_id] = part_cost * part.qty_in_sheet

    return costs


def allocate_material_costs(
    sheet_cost_pln: float,
    sheet: SheetSpec,
    parts: List[PartPlacement],
    model: AllocationModel = AllocationModel.OCCUPIED_AREA,
    utilization: Optional[float] = None
) -> Dict[str, float]:
    """
    Allocate material cost to parts using specified model.

    Args:
        sheet_cost_pln: Total sheet cost [PLN]
        sheet: Sheet specification
        parts: List of part placements
        model: Allocation model to use
        utilization: Pre-calculated utilization (for UTILIZATION_FACTOR model)

    Returns:
        Dict mapping instance_id to material cost [PLN]
    """
    if model == AllocationModel.OCCUPIED_AREA:
        return allocate_material_cost_occupied_area(sheet_cost_pln, parts)
    elif model == AllocationModel.UTILIZATION_FACTOR:
        return allocate_material_cost_utilization(
            sheet_cost_pln, sheet, parts, utilization
        )
    else:
        raise ValueError(f"Unknown allocation model: {model}")


def calculate_part_material_cost_per_piece(
    material_costs: Dict[str, float],
    parts: List[PartPlacement]
) -> Dict[str, float]:
    """
    Convert total material costs to per-piece costs.

    Args:
        material_costs: Dict from allocate_material_costs
        parts: List of part placements

    Returns:
        Dict mapping instance_id to per-piece cost [PLN]
    """
    per_piece = {}
    qty_map = {p.instance_id: p.qty_in_sheet for p in parts}

    for instance_id, total_cost in material_costs.items():
        qty = qty_map.get(instance_id, 1)
        per_piece[instance_id] = total_cost / qty if qty > 0 else total_cost

    return per_piece


# Material density constants [kg/m³]
MATERIAL_DENSITIES = {
    # Steel
    'S235': 7850,
    'S355': 7850,
    'DC01': 7850,
    'DC04': 7850,
    'HARDOX': 7850,

    # Stainless steel
    '1.4301': 7900,
    '1.4404': 7900,
    '1.4541': 7900,
    'INOX': 7900,

    # Aluminum
    'AL': 2700,
    'ALU': 2700,
    'ALUMINIUM': 2700,
    '5754': 2700,
    '6061': 2700,

    # Copper/Brass
    'CU': 8960,
    'BRASS': 8500,

    # Default
    'DEFAULT': 7850,
}


def get_material_density(material_name: str) -> float:
    """Get material density from name."""
    name_upper = material_name.upper()

    for key, density in MATERIAL_DENSITIES.items():
        if key in name_upper:
            return density

    return MATERIAL_DENSITIES['DEFAULT']
