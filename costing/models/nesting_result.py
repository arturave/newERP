"""
Data Models for Nesting and Costing.

Defines the contract between nesting module and costing module.
Based on the JSON structure defined in costing.md specification.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime
import json


class SourceType(Enum):
    """Source type for nesting job."""
    ORDER = "order"
    QUOTATION = "quotation"


class SheetMode(Enum):
    """Sheet sizing mode."""
    FIXED_SHEET = "FIXED_SHEET"
    CUT_TO_LENGTH = "CUT_TO_LENGTH"


class AllocationModel(Enum):
    """Material cost allocation model."""
    OCCUPIED_AREA = "OCCUPIED_AREA"
    UTILIZATION_FACTOR = "UTILIZATION_FACTOR"


@dataclass
class Transform:
    """Part placement transformation."""
    x_mm: float = 0.0
    y_mm: float = 0.0
    rotation_deg: float = 0.0

    def to_dict(self) -> Dict:
        return {
            'x_mm': self.x_mm,
            'y_mm': self.y_mm,
            'rotation_deg': self.rotation_deg
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Transform':
        return cls(
            x_mm=data.get('x_mm', 0.0),
            y_mm=data.get('y_mm', 0.0),
            rotation_deg=data.get('rotation_deg', 0.0)
        )


@dataclass
class ToolpathStats:
    """Toolpath statistics from DXF analysis."""
    cut_length_mm: float = 0.0
    rapid_length_mm: float = 0.0
    pierce_count: int = 0
    contour_count: int = 0
    entity_counts: Dict[str, int] = field(default_factory=dict)
    short_segment_ratio: float = 0.0

    def to_dict(self) -> Dict:
        return {
            'cut_length_mm': self.cut_length_mm,
            'rapid_length_mm': self.rapid_length_mm,
            'pierce_count': self.pierce_count,
            'contour_count': self.contour_count,
            'entity_counts': self.entity_counts,
            'short_segment_ratio': self.short_segment_ratio
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ToolpathStats':
        return cls(
            cut_length_mm=data.get('cut_length_mm', 0.0),
            rapid_length_mm=data.get('rapid_length_mm', 0.0),
            pierce_count=data.get('pierce_count', 0),
            contour_count=data.get('contour_count', 0),
            entity_counts=data.get('entity_counts', {}),
            short_segment_ratio=data.get('short_segment_ratio', 0.0)
        )


@dataclass
class PartInstance:
    """Single part instance on a sheet."""
    part_id: str
    instance_id: str
    idx_code: str = ""
    name: str = ""
    qty_in_sheet: int = 1
    transform: Transform = field(default_factory=Transform)
    dxf_storage_path: str = ""
    occupied_area_mm2: float = 0.0
    net_area_mm2: float = 0.0
    toolpath_stats: Optional[ToolpathStats] = None

    def to_dict(self) -> Dict:
        result = {
            'part_id': self.part_id,
            'instance_id': self.instance_id,
            'idx_code': self.idx_code,
            'name': self.name,
            'qty_in_sheet': self.qty_in_sheet,
            'transform': self.transform.to_dict(),
            'dxf_storage_path': self.dxf_storage_path,
            'occupied_area_mm2': self.occupied_area_mm2,
            'net_area_mm2': self.net_area_mm2,
        }
        if self.toolpath_stats:
            result['toolpath_stats'] = self.toolpath_stats.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Dict) -> 'PartInstance':
        toolpath_stats = None
        if 'toolpath_stats' in data and data['toolpath_stats']:
            toolpath_stats = ToolpathStats.from_dict(data['toolpath_stats'])

        return cls(
            part_id=data.get('part_id', ''),
            instance_id=data.get('instance_id', ''),
            idx_code=data.get('idx_code', ''),
            name=data.get('name', ''),
            qty_in_sheet=data.get('qty_in_sheet', 1),
            transform=Transform.from_dict(data.get('transform', {})),
            dxf_storage_path=data.get('dxf_storage_path', ''),
            occupied_area_mm2=data.get('occupied_area_mm2', 0.0),
            net_area_mm2=data.get('net_area_mm2', 0.0),
            toolpath_stats=toolpath_stats
        )


@dataclass
class NestingSheet:
    """Single sheet in nesting result."""
    sheet_id: str
    sheet_mode: SheetMode = SheetMode.FIXED_SHEET
    material_id: str = ""
    thickness_mm: float = 0.0

    sheet_width_mm: float = 1500.0
    sheet_length_mm_nominal: float = 3000.0

    used_length_y_mm: float = 0.0
    trim_margin_y_mm: float = 10.0

    sheet_area_used_mm2: float = 0.0
    occupied_area_mm2: float = 0.0
    utilization: float = 0.0

    preview_image_path: str = ""

    parts: List[PartInstance] = field(default_factory=list)

    def calculate_metrics(self):
        """Calculate sheet area and utilization from parts."""
        if self.sheet_mode == SheetMode.CUT_TO_LENGTH:
            self.sheet_area_used_mm2 = self.sheet_width_mm * (
                self.used_length_y_mm + self.trim_margin_y_mm
            )
        else:
            self.sheet_area_used_mm2 = self.sheet_width_mm * self.sheet_length_mm_nominal

        self.occupied_area_mm2 = sum(
            p.occupied_area_mm2 * p.qty_in_sheet for p in self.parts
        )

        if self.sheet_area_used_mm2 > 0:
            self.utilization = self.occupied_area_mm2 / self.sheet_area_used_mm2

    def to_dict(self) -> Dict:
        return {
            'sheet_id': self.sheet_id,
            'sheet_mode': self.sheet_mode.value,
            'material_id': self.material_id,
            'thickness_mm': self.thickness_mm,
            'sheet_width_mm': self.sheet_width_mm,
            'sheet_length_mm_nominal': self.sheet_length_mm_nominal,
            'used_length_y_mm': self.used_length_y_mm,
            'trim_margin_y_mm': self.trim_margin_y_mm,
            'sheet_area_used_mm2': self.sheet_area_used_mm2,
            'occupied_area_mm2': self.occupied_area_mm2,
            'utilization': self.utilization,
            'preview_image_path': self.preview_image_path,
            'parts': [p.to_dict() for p in self.parts]
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'NestingSheet':
        sheet_mode = SheetMode(data.get('sheet_mode', 'FIXED_SHEET'))

        sheet = cls(
            sheet_id=data.get('sheet_id', ''),
            sheet_mode=sheet_mode,
            material_id=data.get('material_id', ''),
            thickness_mm=data.get('thickness_mm', 0.0),
            sheet_width_mm=data.get('sheet_width_mm', 1500.0),
            sheet_length_mm_nominal=data.get('sheet_length_mm_nominal', 3000.0),
            used_length_y_mm=data.get('used_length_y_mm', 0.0),
            trim_margin_y_mm=data.get('trim_margin_y_mm', 10.0),
            sheet_area_used_mm2=data.get('sheet_area_used_mm2', 0.0),
            occupied_area_mm2=data.get('occupied_area_mm2', 0.0),
            utilization=data.get('utilization', 0.0),
            preview_image_path=data.get('preview_image_path', ''),
            parts=[PartInstance.from_dict(p) for p in data.get('parts', [])]
        )

        return sheet


@dataclass
class NestingResult:
    """Complete nesting result with all sheets and parts."""
    nesting_run_id: Optional[str] = None
    source_type: SourceType = SourceType.ORDER
    source_id: str = ""
    created_at: str = ""
    machine_profile_id: str = ""

    sheets: List[NestingSheet] = field(default_factory=list)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return {
            'nesting_run_id': self.nesting_run_id,
            'source_type': self.source_type.value,
            'source_id': self.source_id,
            'created_at': self.created_at,
            'machine_profile_id': self.machine_profile_id,
            'sheets': [s.to_dict() for s in self.sheets]
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict) -> 'NestingResult':
        return cls(
            nesting_run_id=data.get('nesting_run_id'),
            source_type=SourceType(data.get('source_type', 'order')),
            source_id=data.get('source_id', ''),
            created_at=data.get('created_at', ''),
            machine_profile_id=data.get('machine_profile_id', ''),
            sheets=[NestingSheet.from_dict(s) for s in data.get('sheets', [])]
        )

    @classmethod
    def from_json(cls, json_str: str) -> 'NestingResult':
        return cls.from_dict(json.loads(json_str))


# Cost Summary Models

@dataclass
class SheetCostBreakdown:
    """Cost breakdown for a single sheet."""
    sheet_id: str

    # Material costs
    sheet_cost_pln: float = 0.0

    # Variant A (price-based)
    cut_cost_a_pln: float = 0.0
    pierce_cost_a_pln: float = 0.0
    foil_cost_a_pln: float = 0.0
    operational_cost_pln: float = 0.0

    # Variant B (time-based)
    cut_time_s: float = 0.0
    pierce_time_s: float = 0.0
    foil_time_s: float = 0.0
    total_time_s: float = 0.0
    laser_cost_b_pln: float = 0.0

    def total_a(self) -> float:
        """Total cost variant A."""
        return (self.sheet_cost_pln + self.cut_cost_a_pln +
                self.pierce_cost_a_pln + self.foil_cost_a_pln +
                self.operational_cost_pln)

    def total_b(self) -> float:
        """Total cost variant B."""
        return (self.sheet_cost_pln + self.laser_cost_b_pln +
                self.operational_cost_pln)

    def to_dict(self) -> Dict:
        return {
            'sheet_id': self.sheet_id,
            'sheet_cost_pln': self.sheet_cost_pln,
            'cut_cost_a_pln': self.cut_cost_a_pln,
            'pierce_cost_a_pln': self.pierce_cost_a_pln,
            'foil_cost_a_pln': self.foil_cost_a_pln,
            'operational_cost_pln': self.operational_cost_pln,
            'cut_time_s': self.cut_time_s,
            'pierce_time_s': self.pierce_time_s,
            'foil_time_s': self.foil_time_s,
            'total_time_s': self.total_time_s,
            'laser_cost_b_pln': self.laser_cost_b_pln,
            'total_a': self.total_a(),
            'total_b': self.total_b()
        }


@dataclass
class PartCostBreakdown:
    """Cost breakdown for a single part instance."""
    instance_id: str
    part_id: str

    material_cost_pln: float = 0.0
    cut_cost_a_pln: float = 0.0
    cut_cost_b_pln: float = 0.0

    def to_dict(self) -> Dict:
        return {
            'instance_id': self.instance_id,
            'part_id': self.part_id,
            'material_cost_pln': self.material_cost_pln,
            'cut_cost_a_pln': self.cut_cost_a_pln,
            'cut_cost_b_pln': self.cut_cost_b_pln
        }


@dataclass
class JobCosts:
    """Job-level costs (per order/quotation)."""
    tech_cost_pln: float = 0.0
    packaging_cost_pln: float = 0.0
    transport_cost_pln: float = 0.0

    def total(self) -> float:
        return self.tech_cost_pln + self.packaging_cost_pln + self.transport_cost_pln

    def to_dict(self) -> Dict:
        return {
            'tech_cost_pln': self.tech_cost_pln,
            'packaging_cost_pln': self.packaging_cost_pln,
            'transport_cost_pln': self.transport_cost_pln,
            'total': self.total()
        }


@dataclass
class CostingSummary:
    """Complete costing summary."""
    allocation_model: AllocationModel = AllocationModel.OCCUPIED_AREA
    buffer_factor: float = 1.25
    machine_profile_id: str = ""

    # Totals
    variant_a_total_pln: float = 0.0
    variant_b_total_pln: float = 0.0

    # Breakdowns
    sheet_costs: List[SheetCostBreakdown] = field(default_factory=list)
    part_costs: List[PartCostBreakdown] = field(default_factory=list)
    job_costs: JobCosts = field(default_factory=JobCosts)

    # Flags for included items
    include_piercing: bool = True
    include_foil_removal: bool = False
    include_punch: bool = False

    def to_dict(self) -> Dict:
        return {
            'allocation_model': self.allocation_model.value,
            'buffer_factor': self.buffer_factor,
            'machine_profile_id': self.machine_profile_id,
            'variant_a': {
                'total_pln': self.variant_a_total_pln,
                'sheets': [s.to_dict() for s in self.sheet_costs]
            },
            'variant_b': {
                'total_pln': self.variant_b_total_pln,
                'sheets': [s.to_dict() for s in self.sheet_costs]
            },
            'job_costs': self.job_costs.to_dict(),
            'per_part': {p.instance_id: p.to_dict() for p in self.part_costs},
            'flags': {
                'include_piercing': self.include_piercing,
                'include_foil_removal': self.include_foil_removal,
                'include_punch': self.include_punch
            }
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
