"""
NewERP - Cost Models
====================
Modele danych dla systemu kosztów zamówień/ofert.

Zapewnia jednoznaczne typy dla wszystkich elementów kalkulacji kosztów
cięcia laserowego, gięcia i materiałów.
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum
import json


class AllocationModel(Enum):
    """Model alokacji kosztów arkusza na części"""
    PROPORTIONAL = "proportional"       # Proporcjonalnie do powierzchni
    PER_UNIT = "per_unit"              # Równo na każdą sztukę
    PER_SHEET = "per_sheet"            # Pełny koszt arkusza na każdy detal
    PER_SHEET_MULTIPLIER = "per_sheet"  # Alias dla kompatybilności


class CostVariant(Enum):
    """Wariant wyceny"""
    A_PRICELIST = "pricelist"   # PLN/m + pierce + folia
    B_TIME = "time"             # PLN/h × czas


class CostType(Enum):
    """Typy kosztów"""
    MATERIAL = "material"
    CUTTING = "cutting"
    ENGRAVING = "engraving"
    FOIL_REMOVAL = "foil"
    BENDING = "bending"
    PIERCING = "piercing"
    ADDITIONAL = "additional"
    OPERATIONAL = "operational"


@dataclass
class PartGeometry:
    """Geometria części - pełne dane do odtworzenia"""
    contour_points: List[Tuple[float, float]]  # Punkty konturu zewnętrznego
    holes: List[List[Tuple[float, float]]] = field(default_factory=list)  # Otwory
    bbox_width: float = 0.0
    bbox_height: float = 0.0
    area_mm2: float = 0.0
    cutting_length_mm: float = 0.0
    engraving_length_mm: float = 0.0
    pierce_count: int = 0  # Liczba przebić (1 + liczba otworów)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'contour_points': self.contour_points,
            'holes': self.holes,
            'bbox_width': self.bbox_width,
            'bbox_height': self.bbox_height,
            'area_mm2': self.area_mm2,
            'cutting_length_mm': self.cutting_length_mm,
            'engraving_length_mm': self.engraving_length_mm,
            'pierce_count': self.pierce_count
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PartGeometry':
        return cls(
            contour_points=data.get('contour_points', []),
            holes=data.get('holes', []),
            bbox_width=data.get('bbox_width', 0.0),
            bbox_height=data.get('bbox_height', 0.0),
            area_mm2=data.get('area_mm2', 0.0),
            cutting_length_mm=data.get('cutting_length_mm', 0.0),
            engraving_length_mm=data.get('engraving_length_mm', 0.0),
            pierce_count=data.get('pierce_count', 0)
        )


@dataclass
class PartCost:
    """Koszty pojedynczej części - jedno źródło prawdy"""
    # Koszty bazowe (obliczone automatycznie)
    material_cost: Decimal = Decimal('0.00')
    cutting_cost: Decimal = Decimal('0.00')
    engraving_cost: Decimal = Decimal('0.00')
    foil_cost: Decimal = Decimal('0.00')
    bending_cost: Decimal = Decimal('0.00')
    piercing_cost: Decimal = Decimal('0.00')
    additional_cost: Decimal = Decimal('0.00')

    # Flagi edycji ręcznej
    is_manual_lm: bool = False      # L+M koszt edytowany ręcznie
    is_manual_bending: bool = False  # Koszt gięcia edytowany ręcznie
    is_manual_additional: bool = False

    # Wartości ręczne (jeśli flagi True)
    manual_lm_value: Decimal = Decimal('0.00')
    manual_bending_value: Decimal = Decimal('0.00')
    manual_additional_value: Decimal = Decimal('0.00')

    @property
    def lm_cost(self) -> Decimal:
        """Koszt L+M (cięcie + grawerowanie)"""
        if self.is_manual_lm:
            return self.manual_lm_value
        return self.cutting_cost + self.engraving_cost

    @property
    def effective_bending_cost(self) -> Decimal:
        """Efektywny koszt gięcia"""
        if self.is_manual_bending:
            return self.manual_bending_value
        return self.bending_cost

    @property
    def effective_additional_cost(self) -> Decimal:
        """Efektywny koszt dodatkowy"""
        if self.is_manual_additional:
            return self.manual_additional_value
        return self.additional_cost

    @property
    def total_unit(self) -> Decimal:
        """Całkowity koszt jednostkowy (bez materiału - alokowany osobno)"""
        return (
            self.lm_cost +
            self.effective_bending_cost +
            self.effective_additional_cost +
            self.foil_cost +
            self.piercing_cost
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def total_with_material(self) -> Decimal:
        """Całkowity koszt jednostkowy z materiałem"""
        return (self.total_unit + self.material_cost).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'material_cost': str(self.material_cost),
            'cutting_cost': str(self.cutting_cost),
            'engraving_cost': str(self.engraving_cost),
            'foil_cost': str(self.foil_cost),
            'bending_cost': str(self.bending_cost),
            'piercing_cost': str(self.piercing_cost),
            'additional_cost': str(self.additional_cost),
            'is_manual_lm': self.is_manual_lm,
            'is_manual_bending': self.is_manual_bending,
            'is_manual_additional': self.is_manual_additional,
            'manual_lm_value': str(self.manual_lm_value),
            'manual_bending_value': str(self.manual_bending_value),
            'manual_additional_value': str(self.manual_additional_value),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PartCost':
        return cls(
            material_cost=Decimal(data.get('material_cost', '0.00')),
            cutting_cost=Decimal(data.get('cutting_cost', '0.00')),
            engraving_cost=Decimal(data.get('engraving_cost', '0.00')),
            foil_cost=Decimal(data.get('foil_cost', '0.00')),
            bending_cost=Decimal(data.get('bending_cost', '0.00')),
            piercing_cost=Decimal(data.get('piercing_cost', '0.00')),
            additional_cost=Decimal(data.get('additional_cost', '0.00')),
            is_manual_lm=data.get('is_manual_lm', False),
            is_manual_bending=data.get('is_manual_bending', False),
            is_manual_additional=data.get('is_manual_additional', False),
            manual_lm_value=Decimal(data.get('manual_lm_value', '0.00')),
            manual_bending_value=Decimal(data.get('manual_bending_value', '0.00')),
            manual_additional_value=Decimal(data.get('manual_additional_value', '0.00')),
        )


@dataclass
class PartData:
    """Pełne dane części do kalkulacji i zapisu"""
    # Identyfikacja
    name: str
    material: str
    thickness: float  # mm
    quantity: int = 1

    # Geometria
    geometry: PartGeometry = field(default_factory=PartGeometry)

    # Dodatkowe właściwości
    bends_count: int = 0
    weight_kg: float = 0.0

    # Koszty
    costs: PartCost = field(default_factory=PartCost)

    # Ścieżki plików (lokalne i storage)
    local_dxf_path: Optional[str] = None
    storage_dxf_path: Optional[str] = None
    thumbnail_base64: Optional[str] = None
    thumbnail_storage_path: Optional[str] = None

    # Metadata
    product_id: Optional[str] = None  # ID produktu w bazie
    source: str = "file"  # "file", "product", "manual"

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'material': self.material,
            'thickness': self.thickness,
            'quantity': self.quantity,
            'geometry': self.geometry.to_dict(),
            'bends_count': self.bends_count,
            'weight_kg': self.weight_kg,
            'costs': self.costs.to_dict(),
            'local_dxf_path': self.local_dxf_path,
            'storage_dxf_path': self.storage_dxf_path,
            'thumbnail_base64': self.thumbnail_base64,
            'thumbnail_storage_path': self.thumbnail_storage_path,
            'product_id': self.product_id,
            'source': self.source,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PartData':
        return cls(
            name=data.get('name', ''),
            material=data.get('material', ''),
            thickness=data.get('thickness', 0.0),
            quantity=data.get('quantity', 1),
            geometry=PartGeometry.from_dict(data.get('geometry', {})),
            bends_count=data.get('bends_count', 0),
            weight_kg=data.get('weight_kg', 0.0),
            costs=PartCost.from_dict(data.get('costs', {})),
            local_dxf_path=data.get('local_dxf_path'),
            storage_dxf_path=data.get('storage_dxf_path'),
            thumbnail_base64=data.get('thumbnail_base64'),
            thumbnail_storage_path=data.get('thumbnail_storage_path'),
            product_id=data.get('product_id'),
            source=data.get('source', 'file'),
        )


@dataclass
class SheetPlacement:
    """Pozycja części na arkuszu"""
    part_index: int  # Indeks w liście parts
    x: float
    y: float
    rotation: float = 0.0  # stopnie
    flipped: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            'part_index': self.part_index,
            'x': self.x,
            'y': self.y,
            'rotation': self.rotation,
            'flipped': self.flipped,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SheetPlacement':
        return cls(
            part_index=data.get('part_index', 0),
            x=data.get('x', 0.0),
            y=data.get('y', 0.0),
            rotation=data.get('rotation', 0.0),
            flipped=data.get('flipped', False),
        )


@dataclass
class SheetResult:
    """Wynik nestingu dla pojedynczego arkusza"""
    index: int
    width: float
    height: float
    placements: List[SheetPlacement] = field(default_factory=list)

    # Statystyki
    efficiency: float = 0.0  # 0-100%
    used_area: float = 0.0
    waste_area: float = 0.0

    # Koszty arkusza
    material_cost: Decimal = Decimal('0.00')
    cutting_cost: Decimal = Decimal('0.00')
    total_cost: Decimal = Decimal('0.00')

    # Obraz arkusza (base64 PNG)
    image_base64: Optional[str] = None
    image_storage_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'index': self.index,
            'width': self.width,
            'height': self.height,
            'placements': [p.to_dict() for p in self.placements],
            'efficiency': self.efficiency,
            'used_area': self.used_area,
            'waste_area': self.waste_area,
            'material_cost': str(self.material_cost),
            'cutting_cost': str(self.cutting_cost),
            'total_cost': str(self.total_cost),
            'image_base64': self.image_base64,
            'image_storage_path': self.image_storage_path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SheetResult':
        return cls(
            index=data.get('index', 0),
            width=data.get('width', 0.0),
            height=data.get('height', 0.0),
            placements=[SheetPlacement.from_dict(p) for p in data.get('placements', [])],
            efficiency=data.get('efficiency', 0.0),
            used_area=data.get('used_area', 0.0),
            waste_area=data.get('waste_area', 0.0),
            material_cost=Decimal(data.get('material_cost', '0.00')),
            cutting_cost=Decimal(data.get('cutting_cost', '0.00')),
            total_cost=Decimal(data.get('total_cost', '0.00')),
            image_base64=data.get('image_base64'),
            image_storage_path=data.get('image_storage_path'),
        )


@dataclass
class NestingState:
    """Pełny stan nestingu do zapisu/odczytu"""
    sheets: List[SheetResult] = field(default_factory=list)
    algorithm_used: str = "rectpack"
    sheet_material: str = ""
    sheet_thickness: float = 0.0
    default_sheet_width: float = 2500.0
    default_sheet_height: float = 1250.0

    # Podsumowanie
    total_sheets: int = 0
    total_efficiency: float = 0.0
    total_material_cost: Decimal = Decimal('0.00')
    total_cutting_cost: Decimal = Decimal('0.00')

    def to_dict(self) -> Dict[str, Any]:
        return {
            'sheets': [s.to_dict() for s in self.sheets],
            'algorithm_used': self.algorithm_used,
            'sheet_material': self.sheet_material,
            'sheet_thickness': self.sheet_thickness,
            'default_sheet_width': self.default_sheet_width,
            'default_sheet_height': self.default_sheet_height,
            'total_sheets': self.total_sheets,
            'total_efficiency': self.total_efficiency,
            'total_material_cost': str(self.total_material_cost),
            'total_cutting_cost': str(self.total_cutting_cost),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NestingState':
        return cls(
            sheets=[SheetResult.from_dict(s) for s in data.get('sheets', [])],
            algorithm_used=data.get('algorithm_used', 'rectpack'),
            sheet_material=data.get('sheet_material', ''),
            sheet_thickness=data.get('sheet_thickness', 0.0),
            default_sheet_width=data.get('default_sheet_width', 2500.0),
            default_sheet_height=data.get('default_sheet_height', 1250.0),
            total_sheets=data.get('total_sheets', 0),
            total_efficiency=data.get('total_efficiency', 0.0),
            total_material_cost=Decimal(data.get('total_material_cost', '0.00')),
            total_cutting_cost=Decimal(data.get('total_cutting_cost', '0.00')),
        )


@dataclass
class CostParams:
    """Parametry kalkulacji kosztów"""
    # Model alokacji
    allocation_model: AllocationModel = AllocationModel.PROPORTIONAL

    # Marża
    markup_percent: float = 0.0

    # Włącz/wyłącz składniki
    include_material: bool = True
    include_cutting: bool = True
    include_foil_removal: bool = True
    include_piercing: bool = True
    include_operational: bool = True

    # Koszty per zlecenie
    tech_cost: float = 50.0
    packaging_cost: float = 100.0
    transport_cost: float = 0.0

    # Koszty per arkusz
    operational_per_sheet: float = 40.0

    # Stawki domyślne (jeśli brak w cennikach)
    default_bending_rate: float = 3.0  # PLN/gięcie
    default_engraving_rate: float = 2.5  # PLN/m
    foil_rate: float = 0.50  # PLN/cm²

    # Wariant wyceny
    variant: CostVariant = CostVariant.A_PRICELIST

    # Wersjonowanie (do audytu)
    pricing_version: str = "default"

    def to_dict(self) -> Dict[str, Any]:
        return {
            'allocation_model': self.allocation_model.value,
            'markup_percent': self.markup_percent,
            'include_material': self.include_material,
            'include_cutting': self.include_cutting,
            'include_foil_removal': self.include_foil_removal,
            'include_piercing': self.include_piercing,
            'include_operational': self.include_operational,
            'tech_cost': self.tech_cost,
            'packaging_cost': self.packaging_cost,
            'transport_cost': self.transport_cost,
            'operational_per_sheet': self.operational_per_sheet,
            'default_bending_rate': self.default_bending_rate,
            'default_engraving_rate': self.default_engraving_rate,
            'foil_rate': self.foil_rate,
            'variant': self.variant.value,
            'pricing_version': self.pricing_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CostParams':
        allocation = data.get('allocation_model', 'proportional')
        if isinstance(allocation, str):
            allocation = AllocationModel(allocation)

        variant = data.get('variant', 'pricelist')
        if isinstance(variant, str):
            variant = CostVariant(variant)

        return cls(
            allocation_model=allocation,
            markup_percent=data.get('markup_percent', 0.0),
            include_material=data.get('include_material', True),
            include_cutting=data.get('include_cutting', True),
            include_foil_removal=data.get('include_foil_removal', True),
            include_piercing=data.get('include_piercing', True),
            include_operational=data.get('include_operational', True),
            tech_cost=data.get('tech_cost', 50.0),
            packaging_cost=data.get('packaging_cost', 100.0),
            transport_cost=data.get('transport_cost', 0.0),
            operational_per_sheet=data.get('operational_per_sheet', 40.0),
            default_bending_rate=data.get('default_bending_rate', 3.0),
            default_engraving_rate=data.get('default_engraving_rate', 2.5),
            foil_rate=data.get('foil_rate', 0.50),
            variant=variant,
            pricing_version=data.get('pricing_version', 'default'),
        )


@dataclass
class OrderCost:
    """Podsumowanie kosztów zamówienia"""
    # Koszty agregowane
    total_material: Decimal = Decimal('0.00')
    total_cutting: Decimal = Decimal('0.00')
    total_engraving: Decimal = Decimal('0.00')
    total_foil: Decimal = Decimal('0.00')
    total_bending: Decimal = Decimal('0.00')
    total_piercing: Decimal = Decimal('0.00')
    total_additional: Decimal = Decimal('0.00')

    # Sumy
    subtotal: Decimal = Decimal('0.00')  # Przed marżą
    markup_amount: Decimal = Decimal('0.00')
    grand_total: Decimal = Decimal('0.00')

    # Statystyki
    total_parts: int = 0
    total_quantity: int = 0
    total_sheets: int = 0
    average_efficiency: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_material': str(self.total_material),
            'total_cutting': str(self.total_cutting),
            'total_engraving': str(self.total_engraving),
            'total_foil': str(self.total_foil),
            'total_bending': str(self.total_bending),
            'total_piercing': str(self.total_piercing),
            'total_additional': str(self.total_additional),
            'subtotal': str(self.subtotal),
            'markup_amount': str(self.markup_amount),
            'grand_total': str(self.grand_total),
            'total_parts': self.total_parts,
            'total_quantity': self.total_quantity,
            'total_sheets': self.total_sheets,
            'average_efficiency': self.average_efficiency,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OrderCost':
        return cls(
            total_material=Decimal(data.get('total_material', '0.00')),
            total_cutting=Decimal(data.get('total_cutting', '0.00')),
            total_engraving=Decimal(data.get('total_engraving', '0.00')),
            total_foil=Decimal(data.get('total_foil', '0.00')),
            total_bending=Decimal(data.get('total_bending', '0.00')),
            total_piercing=Decimal(data.get('total_piercing', '0.00')),
            total_additional=Decimal(data.get('total_additional', '0.00')),
            subtotal=Decimal(data.get('subtotal', '0.00')),
            markup_amount=Decimal(data.get('markup_amount', '0.00')),
            grand_total=Decimal(data.get('grand_total', '0.00')),
            total_parts=data.get('total_parts', 0),
            total_quantity=data.get('total_quantity', 0),
            total_sheets=data.get('total_sheets', 0),
            average_efficiency=data.get('average_efficiency', 0.0),
        )


@dataclass
class OrderState:
    """Pełny stan zamówienia/oferty do zapisu/odczytu"""
    # Identyfikacja
    order_id: Optional[str] = None
    order_number: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: str = ""

    # Status
    status: str = "draft"  # draft, quotation, order, completed
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # Dane główne
    parts: List[PartData] = field(default_factory=list)
    nesting: NestingState = field(default_factory=NestingState)
    cost_params: CostParams = field(default_factory=CostParams)
    cost_result: OrderCost = field(default_factory=OrderCost)

    # Załączniki
    attachments: List[Dict[str, str]] = field(default_factory=list)

    # Notatki
    notes: str = ""
    internal_notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'order_id': self.order_id,
            'order_number': self.order_number,
            'customer_id': self.customer_id,
            'customer_name': self.customer_name,
            'status': self.status,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'parts': [p.to_dict() for p in self.parts],
            'nesting': self.nesting.to_dict(),
            'cost_params': self.cost_params.to_dict(),
            'cost_result': self.cost_result.to_dict(),
            'attachments': self.attachments,
            'notes': self.notes,
            'internal_notes': self.internal_notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OrderState':
        return cls(
            order_id=data.get('order_id'),
            order_number=data.get('order_number'),
            customer_id=data.get('customer_id'),
            customer_name=data.get('customer_name', ''),
            status=data.get('status', 'draft'),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at'),
            parts=[PartData.from_dict(p) for p in data.get('parts', [])],
            nesting=NestingState.from_dict(data.get('nesting', {})),
            cost_params=CostParams.from_dict(data.get('cost_params', {})),
            cost_result=OrderCost.from_dict(data.get('cost_result', {})),
            attachments=data.get('attachments', []),
            notes=data.get('notes', ''),
            internal_notes=data.get('internal_notes', ''),
        )

    def to_json(self) -> str:
        """Serializuj do JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> 'OrderState':
        """Deserializuj z JSON"""
        return cls.from_dict(json.loads(json_str))
