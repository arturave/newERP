"""
Nesting Costing Service - Main service for calculating nesting costs.

Provides two costing variants:
- Variant A (price-based): PLN/m + pierce + foil + operational costs
- Variant B (time-based): PLN/h * estimated_time * buffer + operational costs

Usage:
    service = NestingCostingService()
    result = service.compute_costing(nesting_result, job_overrides, pricing_config)
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path

from ..motion.motion_planner import (
    MachineProfile, estimate_simple_time, estimate_motion_time, m_min_to_mm_s
)
from ..toolpath.dxf_extractor import (
    extract_toolpath_stats, extract_motion_segments, ToolpathStats
)
from ..material.allocation import (
    SheetSpec, SheetMode as AllocSheetMode, MaterialSpec,
    PartPlacement, AllocationModel as AllocModel,
    allocate_material_costs, get_material_density
)
from ..models.nesting_result import (
    NestingResult, NestingSheet, PartInstance, CostingSummary,
    SheetCostBreakdown, PartCostBreakdown, JobCosts,
    AllocationModel, SheetMode
)

logger = logging.getLogger(__name__)


@dataclass
class PricingConfig:
    """Configuration for cutting prices."""
    # Price per meter of cut [PLN/m] - keyed by (material_id, thickness_mm)
    cutting_prices: Dict[str, float] = field(default_factory=dict)

    # Pierce cost [PLN] - keyed by (material_id, thickness_mm)
    pierce_costs: Dict[str, float] = field(default_factory=dict)

    # Pierce time [s] - keyed by (material_id, thickness_mm)
    pierce_times: Dict[str, float] = field(default_factory=dict)

    # Cutting speed [m/min] - keyed by (material_id, thickness_mm)
    cutting_speeds: Dict[str, float] = field(default_factory=dict)

    # Material prices [PLN/kg] - keyed by material_id
    material_prices_per_kg: Dict[str, float] = field(default_factory=dict)

    # Foil removal settings
    foil_removal_speed_m_min: float = 15.0
    foil_cost_per_m2: float = 2.0

    # Machine rate [PLN/h]
    machine_rate_pln_per_h: float = 300.0

    # Operational cost per sheet [PLN]
    operational_cost_per_sheet: float = 40.0

    def get_key(self, material_id: str, thickness_mm: float) -> str:
        """Generate lookup key for material+thickness."""
        return f"{material_id}_{thickness_mm:.1f}"

    def get_cutting_price(self, material_id: str, thickness_mm: float) -> float:
        """Get cutting price per meter [PLN/m]."""
        key = self.get_key(material_id, thickness_mm)
        if key in self.cutting_prices:
            return self.cutting_prices[key]
        # Fallback: estimate from thickness
        return 5.0 + thickness_mm * 2.0  # Base + 2 PLN per mm thickness

    def get_pierce_cost(self, material_id: str, thickness_mm: float) -> float:
        """Get cost per pierce [PLN]."""
        key = self.get_key(material_id, thickness_mm)
        if key in self.pierce_costs:
            return self.pierce_costs[key]
        # Fallback: estimate from thickness
        return 0.5 + thickness_mm * 0.2

    def get_pierce_time(self, material_id: str, thickness_mm: float) -> float:
        """Get time per pierce [s]."""
        key = self.get_key(material_id, thickness_mm)
        if key in self.pierce_times:
            return self.pierce_times[key]
        # Fallback: estimate from thickness
        return 0.5 + thickness_mm * 0.3

    def get_cutting_speed(self, material_id: str, thickness_mm: float) -> float:
        """Get cutting speed [m/min]."""
        key = self.get_key(material_id, thickness_mm)
        if key in self.cutting_speeds:
            return self.cutting_speeds[key]
        # Fallback: estimate (slower for thicker materials)
        base_speed = 6.0  # m/min for thin steel
        return max(0.5, base_speed - thickness_mm * 0.3)

    def get_material_price(self, material_id: str) -> float:
        """Get material price per kg [PLN/kg]."""
        if material_id in self.material_prices_per_kg:
            return self.material_prices_per_kg[material_id]

        # Check for partial matches
        material_upper = material_id.upper()
        for key, price in self.material_prices_per_kg.items():
            if key.upper() in material_upper or material_upper in key.upper():
                return price

        # Fallback
        return 5.0  # Default steel price


@dataclass
class JobOverrides:
    """Job-level cost overrides."""
    tech_cost_pln: float = 0.0
    packaging_cost_pln: float = 0.0
    transport_cost_pln: float = 0.0

    operational_cost_per_sheet_pln: float = 40.0

    include_piercing: bool = True
    include_foil_removal: bool = False
    include_punch: bool = False


class NestingCostingService:
    """
    Main service for calculating nesting costs.

    Supports two costing variants:
    - Variant A: Price-based (PLN/m)
    - Variant B: Time-based (PLN/h)
    """

    def __init__(self, machine_profile: Optional[MachineProfile] = None,
                 use_detailed_motion_planning: bool = True):
        """
        Initialize costing service.

        Args:
            machine_profile: Machine dynamics profile (default if None)
            use_detailed_motion_planning: Use full lookahead algorithm with real segments
        """
        self.machine_profile = machine_profile or MachineProfile()
        self.use_detailed_motion_planning = use_detailed_motion_planning
        self._toolpath_cache: Dict[str, ToolpathStats] = {}
        self._segments_cache: Dict[str, List] = {}  # Cache for detailed segments

    def compute_part_stats_from_dxf(self, dxf_path: str) -> Dict:
        """
        Compute toolpath statistics from DXF file.

        Args:
            dxf_path: Path to DXF file

        Returns:
            Dict with toolpath stats
        """
        if dxf_path in self._toolpath_cache:
            stats = self._toolpath_cache[dxf_path]
        else:
            stats = extract_toolpath_stats(dxf_path)
            self._toolpath_cache[dxf_path] = stats

        return {
            'cut_length_mm': stats.cut_length_mm,
            'rapid_length_mm': stats.rapid_length_mm,
            'pierce_count': stats.pierce_count,
            'contour_count': stats.contour_count,
            'entity_counts': stats.entity_counts,
            'short_segment_ratio': stats.short_segment_ratio,
            'occupied_area_mm2': stats.occupied_area_mm2,
            'net_area_mm2': stats.net_area_mm2
        }

    def estimate_sheet_times(
        self,
        sheet: NestingSheet,
        pricing: PricingConfig
    ) -> Dict[str, float]:
        """
        Estimate cutting times for a sheet.

        Args:
            sheet: Sheet with parts
            pricing: Pricing configuration

        Returns:
            Dict with time estimates
        """
        total_cut_time = 0.0
        total_pierce_time = 0.0
        total_foil_time = 0.0

        v_max = pricing.get_cutting_speed(sheet.material_id, sheet.thickness_mm)
        pierce_time = pricing.get_pierce_time(sheet.material_id, sheet.thickness_mm)

        for part in sheet.parts:
            stats = part.toolpath_stats
            if not stats:
                continue

            # Try detailed motion planning if enabled and DXF available
            cut_time = 0.0
            if self.use_detailed_motion_planning and part.dxf_storage_path:
                try:
                    # Try to get cached segments
                    dxf_path = part.dxf_storage_path
                    if dxf_path not in self._segments_cache:
                        segments = extract_motion_segments(str(dxf_path))
                        self._segments_cache[dxf_path] = segments
                    else:
                        segments = self._segments_cache[dxf_path]

                    # Use detailed motion planning with full lookahead
                    v_max_mm_s = m_min_to_mm_s(v_max)
                    cut_time, rapid_time = estimate_motion_time(
                        segments, self.machine_profile, v_max_mm_s
                    )
                    logger.debug(f"Part {part.idx_code}: detailed motion time = {cut_time:.2f}s")
                except Exception as e:
                    logger.warning(f"Detailed motion planning failed for {part.idx_code}: {e}")
                    cut_time = 0.0

            # Fallback to simplified model if detailed planning unavailable
            if cut_time == 0.0:
                cut_time = estimate_simple_time(
                    cut_length_mm=stats.cut_length_mm,
                    pierce_count=0,  # Counted separately
                    short_segment_ratio=stats.short_segment_ratio,
                    v_max_m_min=v_max,
                    a_max_mm_s2=self.machine_profile.max_accel_mm_s2,
                    v_corner_90_mm_s=self.machine_profile.square_corner_velocity_mm_s,
                    pierce_time_s=0
                )

            total_cut_time += cut_time * part.qty_in_sheet
            total_pierce_time += stats.pierce_count * pierce_time * part.qty_in_sheet

        # Foil removal time (if enabled)
        if sheet.sheet_area_used_mm2 > 0:
            foil_area_m2 = sheet.sheet_area_used_mm2 / 1_000_000
            foil_distance_m = foil_area_m2 * 100  # Approximate: 100m per m²
            total_foil_time = (foil_distance_m / pricing.foil_removal_speed_m_min) * 60

        return {
            'cut_time_s': total_cut_time,
            'pierce_time_s': total_pierce_time,
            'foil_time_s': total_foil_time,
            'total_base_time_s': total_cut_time + total_pierce_time
        }

    def allocate_material_costs(
        self,
        sheet: NestingSheet,
        sheet_cost_pln: float,
        allocation_model: AllocationModel = AllocationModel.OCCUPIED_AREA
    ) -> Dict[str, float]:
        """
        Allocate sheet material cost to parts.

        Args:
            sheet: Sheet with parts
            sheet_cost_pln: Total sheet cost
            allocation_model: Allocation method

        Returns:
            Dict mapping instance_id to material cost
        """
        # Convert to allocation module types
        spec = SheetSpec(
            width_mm=sheet.sheet_width_mm,
            length_mm_nominal=sheet.sheet_length_mm_nominal,
            used_length_y_mm=sheet.used_length_y_mm,
            trim_margin_y_mm=sheet.trim_margin_y_mm,
            mode=(AllocSheetMode.CUT_TO_LENGTH
                  if sheet.sheet_mode == SheetMode.CUT_TO_LENGTH
                  else AllocSheetMode.FIXED_SHEET)
        )

        placements = [
            PartPlacement(
                part_id=p.part_id,
                instance_id=p.instance_id,
                occupied_area_mm2=p.occupied_area_mm2,
                net_area_mm2=p.net_area_mm2,
                qty_in_sheet=p.qty_in_sheet
            )
            for p in sheet.parts
        ]

        model = (AllocModel.OCCUPIED_AREA
                 if allocation_model == AllocationModel.OCCUPIED_AREA
                 else AllocModel.UTILIZATION_FACTOR)

        return allocate_material_costs(
            sheet_cost_pln, spec, placements, model, sheet.utilization
        )

    def compute_costing(
        self,
        nesting_result: NestingResult,
        job_overrides: JobOverrides,
        pricing: PricingConfig,
        allocation_model: AllocationModel = AllocationModel.OCCUPIED_AREA,
        buffer_factor: float = 1.25
    ) -> CostingSummary:
        """
        Compute complete costing for nesting result.

        Calculates both Variant A (price-based) and Variant B (time-based).

        Args:
            nesting_result: Nesting result with sheets and parts
            job_overrides: Job-level cost settings
            pricing: Pricing configuration
            allocation_model: Material cost allocation method
            buffer_factor: Time buffer multiplier for Variant B (default 1.25 = +25%)

        Returns:
            CostingSummary with complete breakdown
        """
        summary = CostingSummary(
            allocation_model=allocation_model,
            buffer_factor=buffer_factor,
            machine_profile_id=nesting_result.machine_profile_id,
            include_piercing=job_overrides.include_piercing,
            include_foil_removal=job_overrides.include_foil_removal,
            include_punch=job_overrides.include_punch
        )

        # Job costs
        summary.job_costs = JobCosts(
            tech_cost_pln=job_overrides.tech_cost_pln,
            packaging_cost_pln=job_overrides.packaging_cost_pln,
            transport_cost_pln=job_overrides.transport_cost_pln
        )

        total_a = 0.0
        total_b = 0.0

        for sheet in nesting_result.sheets:
            sheet_breakdown = self._calculate_sheet_costs(
                sheet, pricing, job_overrides, allocation_model, buffer_factor, summary
            )
            summary.sheet_costs.append(sheet_breakdown)

            total_a += sheet_breakdown.total_a()
            total_b += sheet_breakdown.total_b()

        # Add job costs
        total_a += summary.job_costs.total()
        total_b += summary.job_costs.total()

        summary.variant_a_total_pln = total_a
        summary.variant_b_total_pln = total_b

        logger.info(f"Costing complete: A={total_a:.2f} PLN, B={total_b:.2f} PLN")

        return summary

    def _calculate_sheet_costs(
        self,
        sheet: NestingSheet,
        pricing: PricingConfig,
        job_overrides: JobOverrides,
        allocation_model: AllocationModel,
        buffer_factor: float,
        summary: CostingSummary
    ) -> SheetCostBreakdown:
        """Calculate costs for a single sheet."""
        breakdown = SheetCostBreakdown(sheet_id=sheet.sheet_id)

        # Material cost
        material_price = pricing.get_material_price(sheet.material_id)
        density = get_material_density(sheet.material_id)

        # Sheet area in m²
        area_m2 = sheet.sheet_area_used_mm2 / 1_000_000
        thickness_m = sheet.thickness_mm / 1000

        mass_kg = area_m2 * thickness_m * density
        breakdown.sheet_cost_pln = mass_kg * material_price

        # Allocate material costs to parts
        part_material_costs = self.allocate_material_costs(
            sheet, breakdown.sheet_cost_pln, allocation_model
        )

        # Estimate times
        times = self.estimate_sheet_times(sheet, pricing)

        breakdown.cut_time_s = times['cut_time_s']
        breakdown.pierce_time_s = times['pierce_time_s']
        breakdown.foil_time_s = times['foil_time_s']

        # Operational cost
        breakdown.operational_cost_pln = job_overrides.operational_cost_per_sheet_pln

        # Variant A: Price-based
        total_cut_length_m = sum(
            (p.toolpath_stats.cut_length_mm if p.toolpath_stats else 0) * p.qty_in_sheet
            for p in sheet.parts
        ) / 1000.0

        total_pierces = sum(
            (p.toolpath_stats.pierce_count if p.toolpath_stats else 0) * p.qty_in_sheet
            for p in sheet.parts
        )

        cutting_price = pricing.get_cutting_price(sheet.material_id, sheet.thickness_mm)
        breakdown.cut_cost_a_pln = total_cut_length_m * cutting_price

        if job_overrides.include_piercing:
            pierce_cost = pricing.get_pierce_cost(sheet.material_id, sheet.thickness_mm)
            breakdown.pierce_cost_a_pln = total_pierces * pierce_cost

        if job_overrides.include_foil_removal:
            breakdown.foil_cost_a_pln = area_m2 * pricing.foil_cost_per_m2

        # Variant B: Time-based
        base_time_s = breakdown.cut_time_s

        if job_overrides.include_piercing:
            base_time_s += breakdown.pierce_time_s

        if job_overrides.include_foil_removal:
            base_time_s += breakdown.foil_time_s

        breakdown.total_time_s = base_time_s * buffer_factor
        breakdown.laser_cost_b_pln = (breakdown.total_time_s / 3600) * pricing.machine_rate_pln_per_h

        # Per-part cost breakdown
        for part in sheet.parts:
            part_breakdown = PartCostBreakdown(
                instance_id=part.instance_id,
                part_id=part.part_id,
                material_cost_pln=part_material_costs.get(part.instance_id, 0.0)
            )

            # Allocate cutting costs proportionally to cut length
            if total_cut_length_m > 0 and part.toolpath_stats:
                part_cut_length_m = part.toolpath_stats.cut_length_mm * part.qty_in_sheet / 1000.0
                ratio = part_cut_length_m / total_cut_length_m

                part_breakdown.cut_cost_a_pln = breakdown.cut_cost_a_pln * ratio
                part_breakdown.cut_cost_b_pln = breakdown.laser_cost_b_pln * ratio

            summary.part_costs.append(part_breakdown)

        return breakdown


def create_default_pricing() -> PricingConfig:
    """Create default pricing configuration."""
    pricing = PricingConfig()

    # Default cutting prices [PLN/m] for steel
    for thickness in [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]:
        key = f"S355_{thickness:.1f}"
        pricing.cutting_prices[key] = 3.0 + thickness * 1.5

        key = f"S235_{thickness:.1f}"
        pricing.cutting_prices[key] = 3.0 + thickness * 1.5

    # Stainless steel (higher prices)
    for thickness in [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0]:
        key = f"1.4301_{thickness:.1f}"
        pricing.cutting_prices[key] = 8.0 + thickness * 3.0

    # Default cutting speeds [m/min]
    for thickness in [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]:
        key = f"S355_{thickness:.1f}"
        pricing.cutting_speeds[key] = max(0.5, 8.0 - thickness * 0.4)

        key = f"1.4301_{thickness:.1f}"
        pricing.cutting_speeds[key] = max(0.3, 6.0 - thickness * 0.5)

    # Default pierce times [s]
    for thickness in [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]:
        key = f"S355_{thickness:.1f}"
        pricing.pierce_times[key] = 0.3 + thickness * 0.2

    # Material prices [PLN/kg]
    pricing.material_prices_per_kg = {
        'S355': 4.5,
        'S235': 4.2,
        'DC01': 5.0,
        'DC04': 5.2,
        '1.4301': 18.0,
        '1.4404': 22.0,
        'AL': 12.0,
        'ALUMINIUM': 12.0,
    }

    return pricing
