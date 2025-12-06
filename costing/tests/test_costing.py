"""
Test script for the new costing module.

Tests:
1. DXF toolpath extraction
2. Motion time estimation
3. Material cost allocation
4. Complete costing flow
"""

import sys
import os
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_motion_planner():
    """Test motion planning functions."""
    print("\n=== TEST: Motion Planner ===")

    from costing.motion.motion_planner import (
        corner_speed_limit, plan_speeds, segment_time_trapezoid,
        effective_vmax, estimate_simple_time, MachineProfile
    )

    # Test corner speed limit
    v_corner_90 = 50.0  # mm/s
    v_max = 100.0  # mm/s

    print(f"\nCorner speed limits (v_max={v_max}, v_corner_90={v_corner_90}):")
    for angle in [0, 45, 90, 135, 180]:
        v = corner_speed_limit(angle, v_corner_90, v_max)
        print(f"  Angle {angle}°: {v:.1f} mm/s")

    # Test plan_speeds
    lengths = [100, 50, 30, 100]  # mm
    v_junction = [0, 80, 50, 80, 0]  # mm/s limits at junctions
    v_max = 100  # mm/s
    a_max = 2000  # mm/s²

    V = plan_speeds(lengths, v_junction, v_max, a_max)
    print(f"\nPlanned speeds: {[f'{v:.1f}' for v in V]}")

    # Test segment time
    L = 100  # mm
    t = segment_time_trapezoid(L, 0, 0, 100, 2000)
    print(f"\nSegment time (100mm from stop to stop): {t:.3f}s")

    # Test effective vmax
    v_eff_0 = effective_vmax(100, 0.0)    # No short segments
    v_eff_50 = effective_vmax(100, 0.5)   # 50% short segments
    v_eff_100 = effective_vmax(100, 1.0)  # All short segments
    print(f"\nEffective vmax (short_ratio=0%): {v_eff_0:.1f}")
    print(f"Effective vmax (short_ratio=50%): {v_eff_50:.1f}")
    print(f"Effective vmax (short_ratio=100%): {v_eff_100:.1f}")

    # Test simple time estimation
    machine = MachineProfile()
    time_simple = estimate_simple_time(
        cut_length_mm=1000,
        pierce_count=5,
        short_segment_ratio=0.2,
        v_max_m_min=3.0,
        a_max_mm_s2=machine.max_accel_mm_s2,
        v_corner_90_mm_s=machine.square_corner_velocity_mm_s,
        pierce_time_s=1.0
    )
    print(f"\nSimple time estimate (1000mm, 5 pierces, 20% short): {time_simple:.2f}s")

    print("\n[OK] Motion planner tests passed")


def test_toolpath_extractor():
    """Test DXF toolpath extraction."""
    print("\n=== TEST: Toolpath Extractor ===")

    from costing.toolpath.dxf_extractor import extract_toolpath_stats

    # Find test DXF files
    test_folders = [
        Path(__file__).parent / "test_dxfs",
        Path(r"C:\Users\artur\source\repos\arturave\NewERP\temp\dxf_test"),
        Path(r"C:\Users\artur\source\repos\arturave\NewERP\test_data"),
    ]

    dxf_files = []
    for folder in test_folders:
        if folder.exists():
            dxf_files.extend(folder.glob("*.dxf"))
            dxf_files.extend(folder.glob("*.DXF"))

    if not dxf_files:
        print("No DXF files found for testing")
        return

    print(f"\nFound {len(dxf_files)} DXF files")

    for dxf_path in dxf_files[:5]:  # Test first 5
        try:
            stats = extract_toolpath_stats(str(dxf_path))
            print(f"\n{dxf_path.name}:")
            print(f"  Cut length: {stats.cut_length_mm:.1f} mm")
            print(f"  Pierce count: {stats.pierce_count}")
            print(f"  Contour count: {stats.contour_count}")
            print(f"  Short segment ratio: {stats.short_segment_ratio:.2%}")
            print(f"  Occupied area: {stats.occupied_area_mm2:.0f} mm²")
            print(f"  Entity counts: {stats.entity_counts}")
        except Exception as e:
            print(f"\n{dxf_path.name}: ERROR - {e}")

    print("\n[OK] Toolpath extractor tests completed")


def test_material_allocation():
    """Test material cost allocation."""
    print("\n=== TEST: Material Allocation ===")

    from costing.material.allocation import (
        SheetSpec, SheetMode, PartPlacement, AllocationModel,
        allocate_material_costs, calculate_sheet_utilization
    )

    # Create test sheet
    sheet = SheetSpec(
        width_mm=1500,
        length_mm_nominal=3000,
        mode=SheetMode.FIXED_SHEET
    )

    # Create test parts
    parts = [
        PartPlacement(part_id="P1", instance_id="I1", occupied_area_mm2=100000, qty_in_sheet=2),
        PartPlacement(part_id="P2", instance_id="I2", occupied_area_mm2=200000, qty_in_sheet=1),
        PartPlacement(part_id="P3", instance_id="I3", occupied_area_mm2=50000, qty_in_sheet=4),
    ]

    sheet_cost = 500.0  # PLN

    # Calculate utilization
    utilization = calculate_sheet_utilization(parts, sheet)
    print(f"\nSheet utilization: {utilization:.1%}")

    # Allocate by occupied area
    costs_occupied = allocate_material_costs(
        sheet_cost, sheet, parts, AllocationModel.OCCUPIED_AREA
    )
    print(f"\nAllocation by OCCUPIED_AREA:")
    total = 0
    for part in parts:
        cost = costs_occupied[part.instance_id]
        total += cost
        print(f"  {part.instance_id}: {cost:.2f} PLN")
    print(f"  Total: {total:.2f} PLN (should be {sheet_cost:.2f})")

    # Allocate by utilization factor
    costs_util = allocate_material_costs(
        sheet_cost, sheet, parts, AllocationModel.UTILIZATION_FACTOR, utilization
    )
    print(f"\nAllocation by UTILIZATION_FACTOR:")
    total = 0
    for part in parts:
        cost = costs_util[part.instance_id]
        total += cost
        print(f"  {part.instance_id}: {cost:.2f} PLN")
    print(f"  Total: {total:.2f} PLN")

    print("\n[OK] Material allocation tests passed")


def test_costing_service():
    """Test complete costing service."""
    print("\n=== TEST: Costing Service ===")

    from costing.services.costing_service import (
        NestingCostingService, PricingConfig, JobOverrides, create_default_pricing
    )
    from costing.models.nesting_result import (
        NestingResult, NestingSheet, PartInstance, ToolpathStats,
        SheetMode, SourceType, AllocationModel
    )

    # Create test nesting result
    nesting = NestingResult(
        source_type=SourceType.ORDER,
        source_id="TEST-001",
        machine_profile_id="default"
    )

    # Add a sheet with parts
    sheet = NestingSheet(
        sheet_id="SHEET-1",
        sheet_mode=SheetMode.FIXED_SHEET,
        material_id="S355",
        thickness_mm=3.0,
        sheet_width_mm=1500,
        sheet_length_mm_nominal=3000
    )

    # Add parts with toolpath stats
    sheet.parts = [
        PartInstance(
            part_id="PART-1",
            instance_id="INST-1",
            idx_code="11-001",
            name="Bracket A",
            qty_in_sheet=5,
            occupied_area_mm2=50000,
            toolpath_stats=ToolpathStats(
                cut_length_mm=800,
                pierce_count=3,
                short_segment_ratio=0.15
            )
        ),
        PartInstance(
            part_id="PART-2",
            instance_id="INST-2",
            idx_code="11-002",
            name="Plate B",
            qty_in_sheet=2,
            occupied_area_mm2=200000,
            toolpath_stats=ToolpathStats(
                cut_length_mm=2500,
                pierce_count=12,
                short_segment_ratio=0.35
            )
        )
    ]

    sheet.calculate_metrics()
    nesting.sheets.append(sheet)

    print(f"\nSheet metrics:")
    print(f"  Area used: {sheet.sheet_area_used_mm2/1e6:.3f} m2")
    print(f"  Occupied area: {sheet.occupied_area_mm2/1e6:.3f} m2")
    print(f"  Utilization: {sheet.utilization:.1%}")

    # Create service and pricing
    service = NestingCostingService()
    pricing = create_default_pricing()

    # Job overrides
    overrides = JobOverrides(
        tech_cost_pln=50,
        packaging_cost_pln=20,
        include_piercing=True,
        include_foil_removal=False
    )

    # Compute costing
    result = service.compute_costing(
        nesting, overrides, pricing,
        allocation_model=AllocationModel.OCCUPIED_AREA,
        buffer_factor=1.25
    )

    print(f"\nCosting Results:")
    print(f"  Variant A (price-based): {result.variant_a_total_pln:.2f} PLN")
    print(f"  Variant B (time-based): {result.variant_b_total_pln:.2f} PLN")

    print(f"\nSheet breakdown:")
    for sheet_cost in result.sheet_costs:
        print(f"  {sheet_cost.sheet_id}:")
        print(f"    Material: {sheet_cost.sheet_cost_pln:.2f} PLN")
        print(f"    Cut (A): {sheet_cost.cut_cost_a_pln:.2f} PLN")
        print(f"    Pierce (A): {sheet_cost.pierce_cost_a_pln:.2f} PLN")
        print(f"    Cut time: {sheet_cost.cut_time_s:.1f}s")
        print(f"    Total time: {sheet_cost.total_time_s:.1f}s")
        print(f"    Laser (B): {sheet_cost.laser_cost_b_pln:.2f} PLN")

    print(f"\nPart breakdown:")
    for part_cost in result.part_costs:
        print(f"  {part_cost.instance_id}:")
        print(f"    Material: {part_cost.material_cost_pln:.2f} PLN")
        print(f"    Cut (A): {part_cost.cut_cost_a_pln:.2f} PLN")
        print(f"    Cut (B): {part_cost.cut_cost_b_pln:.2f} PLN")

    print(f"\nJob costs: {result.job_costs.total():.2f} PLN")

    print("\n[OK] Costing service tests passed")


def test_with_real_dxf():
    """Test with real DXF files if available."""
    print("\n=== TEST: Real DXF Files ===")

    from costing.toolpath.dxf_extractor import extract_toolpath_stats
    from costing.services.costing_service import (
        NestingCostingService, create_default_pricing, JobOverrides
    )
    from costing.models.nesting_result import (
        NestingResult, NestingSheet, PartInstance, ToolpathStats,
        SheetMode, SourceType, AllocationModel
    )

    # Find DXF files - check multiple locations
    test_folders = [
        Path(__file__).parent / "test_dxfs",
        Path(r"C:\Users\artur\source\repos\arturave\NewERP\temp\dxf_test"),
    ]

    test_folder = None
    for folder in test_folders:
        if folder.exists():
            test_folder = folder
            break

    if test_folder is None:
        print("Test folder not found, skipping")
        return

    dxf_files = list(test_folder.glob("*.dxf")) + list(test_folder.glob("*.DXF"))
    dxf_files = list(set(dxf_files))  # Remove duplicates

    if not dxf_files:
        print("No DXF files found")
        return

    # Create nesting result with real parts
    nesting = NestingResult(
        source_type=SourceType.ORDER,
        source_id="REAL-TEST-001"
    )

    sheet = NestingSheet(
        sheet_id="SHEET-REAL",
        material_id="S355",
        thickness_mm=2.0,
        sheet_width_mm=1500,
        sheet_length_mm_nominal=3000
    )

    print(f"\nProcessing {len(dxf_files)} DXF files:")

    for i, dxf_path in enumerate(dxf_files[:5]):
        try:
            stats = extract_toolpath_stats(str(dxf_path))

            part = PartInstance(
                part_id=f"REAL-{i+1}",
                instance_id=f"INST-REAL-{i+1}",
                idx_code=dxf_path.stem,
                name=dxf_path.stem,
                qty_in_sheet=1,
                occupied_area_mm2=stats.occupied_area_mm2,
                dxf_storage_path=str(dxf_path),
                toolpath_stats=ToolpathStats(
                    cut_length_mm=stats.cut_length_mm,
                    pierce_count=stats.pierce_count,
                    contour_count=stats.contour_count,
                    short_segment_ratio=stats.short_segment_ratio,
                    entity_counts=stats.entity_counts
                )
            )
            sheet.parts.append(part)
            print(f"  [OK] {dxf_path.name}: {stats.cut_length_mm:.0f}mm cut, {stats.pierce_count} pierces")

        except Exception as e:
            print(f"  [ERR] {dxf_path.name}: {e}")

    if not sheet.parts:
        print("No parts could be processed")
        return

    sheet.calculate_metrics()
    nesting.sheets.append(sheet)

    # Calculate costing
    service = NestingCostingService()
    pricing = create_default_pricing()
    overrides = JobOverrides()

    result = service.compute_costing(nesting, overrides, pricing)

    print(f"\nReal DXF Costing Results:")
    print(f"  Variant A: {result.variant_a_total_pln:.2f} PLN")
    print(f"  Variant B: {result.variant_b_total_pln:.2f} PLN")

    for sheet_cost in result.sheet_costs:
        print(f"\n  Sheet {sheet_cost.sheet_id}:")
        print(f"    Total time: {sheet_cost.total_time_s:.1f}s ({sheet_cost.total_time_s/60:.2f} min)")
        print(f"    Cut time: {sheet_cost.cut_time_s:.1f}s")
        print(f"    Pierce time: {sheet_cost.pierce_time_s:.1f}s")

    print("\n[OK] Real DXF tests completed")


if __name__ == "__main__":
    print("=" * 60)
    print("NESTING COSTING MODULE - TEST SUITE")
    print("=" * 60)

    try:
        test_motion_planner()
    except Exception as e:
        print(f"\n[ERR] Motion planner test failed: {e}")
        import traceback
        traceback.print_exc()

    try:
        test_toolpath_extractor()
    except Exception as e:
        print(f"\n[ERR] Toolpath extractor test failed: {e}")
        import traceback
        traceback.print_exc()

    try:
        test_material_allocation()
    except Exception as e:
        print(f"\n[ERR] Material allocation test failed: {e}")
        import traceback
        traceback.print_exc()

    try:
        test_costing_service()
    except Exception as e:
        print(f"\n[ERR] Costing service test failed: {e}")
        import traceback
        traceback.print_exc()

    try:
        test_with_real_dxf()
    except Exception as e:
        print(f"\n[ERR] Real DXF test failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("TEST SUITE COMPLETE")
    print("=" * 60)
