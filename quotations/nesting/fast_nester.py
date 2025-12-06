"""
Fast Nester - Szybki nesting oparty na rectpack
===============================================
Używa bounding box do pakowania, ale przechowuje prawdziwe kształty do wizualizacji.
Zawiera inteligentne obliczanie kosztów materiału.

Obsługuje WIELE ARKUSZY - jeśli detale nie mieszczą się na jednym arkuszu,
automatycznie dodaje kolejne.

Metoda alokacji kosztów:
1. Po nestingu zmniejsz arkusz do efektywnego rozmiaru (sheet_width × used_height)
2. Oblicz koszt użytej części arkusza proporcjonalnie
3. Rozdziel koszt między detale proporcjonalnie do ich pola powierzchni (contour_area)

Tryby:
- Szybki (default): 3 próby, ~1s
- Głęboka analiza: setki prób z różnymi algorytmami, sortowaniami i tasowaniem
"""

import math
import time
import random
import threading
import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Callable, Dict, Any

logger = logging.getLogger(__name__)

try:
    import rectpack
    HAS_RECTPACK = True
    
    PACKING_ALGORITHMS = [
        rectpack.MaxRectsBl,
        rectpack.MaxRectsBssf,
        rectpack.MaxRectsBaf,
        rectpack.MaxRectsBlsf,
    ]
    
    SORT_ALGORITHMS = [
        rectpack.SORT_AREA,
        rectpack.SORT_PERI,
        rectpack.SORT_DIFF,
        rectpack.SORT_SSIDE,
        rectpack.SORT_LSIDE,
        rectpack.SORT_RATIO,
    ]
    
except ImportError:
    HAS_RECTPACK = False
    PACKING_ALGORITHMS = []
    SORT_ALGORITHMS = []
    logger.warning("rectpack not installed. Run: pip install rectpack")

SCALE = 20  # 0.05 mm precision


@dataclass
class NestedPart:
    """Detal umieszczony na arkuszu"""
    name: str
    x: float
    y: float
    width: float
    height: float
    rotation: float
    
    original_contour: List[Tuple[float, float]] = field(default_factory=list)
    holes: List[List[Tuple[float, float]]] = field(default_factory=list)
    
    orig_width: float = 0.0
    orig_height: float = 0.0
    
    contour_area: float = 0.0
    weight_kg: float = 0.0
    material_cost: float = 0.0

    # Cutting time fields
    cut_length_mm: float = 0.0          # Total cutting length [mm]
    pierce_count: int = 0                # Number of pierces (contour starts)
    cut_time_classic_s: float = 0.0     # Classic time (length/speed) [s]
    cut_time_dynamic_s: float = 0.0     # Dynamic time (motion planner) [s]
    filepath: str = ""                   # Source DXF file path

    source_part_name: str = ""
    part_index: int = 0
    sheet_index: int = 0  # Na którym arkuszu jest detal
    
    def get_placed_contour(self) -> List[Tuple[float, float]]:
        """Zwróć kontur umieszczony na arkuszu"""
        if not self.original_contour:
            return [
                (self.x, self.y),
                (self.x + self.width, self.y),
                (self.x + self.width, self.y + self.height),
                (self.x, self.y + self.height),
                (self.x, self.y)
            ]
        
        result = []
        for px, py in self.original_contour:
            if self.rotation == 90:
                o_w = self.orig_width if self.orig_width > 0 else self.width
                rx = py
                ry = o_w - px
                result.append((self.x + rx, self.y + ry))
            else:
                result.append((self.x + px, self.y + py))
        return result
    
    def get_placed_holes(self) -> List[List[Tuple[float, float]]]:
        """Zwróć otwory umieszczone na arkuszu"""
        if not self.original_contour:
            return []
        
        placed_holes = []
        for hole in self.holes:
            placed_hole = []
            for px, py in hole:
                if self.rotation == 90:
                    o_w = self.orig_width if self.orig_width > 0 else self.width
                    rx = py
                    ry = o_w - px
                    placed_hole.append((self.x + rx, self.y + ry))
                else:
                    placed_hole.append((self.x + px, self.y + py))
            placed_holes.append(placed_hole)
        return placed_holes


@dataclass
class UnplacedPart:
    """Detal który nie zmieścił się na żadnym arkuszu"""
    name: str
    width: float
    height: float
    contour_area: float = 0.0
    reason: str = "Za duży"  # Powód nieumieszczenia
    source_part_name: str = ""
    part_index: int = 0


@dataclass
class PartCostBreakdown:
    """Szczegółowy podział kosztów dla typu detalu"""
    part_name: str
    quantity: int
    unit_weight_kg: float
    total_weight_kg: float
    unit_contour_area: float
    total_contour_area: float
    share_of_used_area: float
    unit_material_cost: float
    total_material_cost: float


@dataclass
class SheetResult:
    """Wynik nestingu dla pojedynczego arkusza"""
    sheet_index: int
    placed_parts: List[NestedPart] = field(default_factory=list)

    sheet_width: float = 0.0
    sheet_height: float = 0.0
    used_width: float = 0.0
    used_height: float = 0.0

    total_parts_area: float = 0.0
    used_sheet_area: float = 0.0
    efficiency: float = 0.0

    sheet_cost: float = 0.0
    used_sheet_cost: float = 0.0

    # Cutting time aggregates for this sheet
    total_cut_length_mm: float = 0.0     # Sum of all parts cutting length
    total_pierce_count: int = 0           # Sum of all parts pierces
    cut_time_classic_s: float = 0.0      # Sum of classic times
    cut_time_dynamic_s: float = 0.0      # Sum of dynamic times


@dataclass
class NestingResult:
    """Wynik nestingu z pełnymi danymi kosztowymi - może zawierać wiele arkuszy"""
    # Wszystkie arkusze
    sheets: List[SheetResult] = field(default_factory=list)
    
    # Wszystkie umieszczone detale (dla kompatybilności wstecznej)
    placed_parts: List[NestedPart] = field(default_factory=list)
    
    # Detale które nie zmieściły się
    unplaced_parts: List[UnplacedPart] = field(default_factory=list)
    unplaced_count: int = 0
    
    # Statystyki globalne
    sheets_used: int = 1
    total_efficiency: float = 0.0
    
    # Wymiary pojedynczego arkusza (dla kompatybilności)
    sheet_width: float = 0.0
    sheet_height: float = 0.0
    used_width: float = 0.0
    used_height: float = 0.0
    efficiency: float = 0.0
    
    # Dane kosztowe globalne
    total_parts_area: float = 0.0
    used_sheet_area: float = 0.0
    effective_utilization: float = 0.0
    
    sheet_cost: float = 0.0
    used_sheet_cost: float = 0.0
    total_cost: float = 0.0

    # Cutting time totals across all sheets
    total_cut_length_mm: float = 0.0     # Sum of all cutting lengths
    total_pierce_count: int = 0           # Sum of all pierces
    cut_time_classic_s: float = 0.0      # Total classic time [s]
    cut_time_dynamic_s: float = 0.0      # Total dynamic time [s]

    cost_breakdown: List[PartCostBreakdown] = field(default_factory=list)
    
    def calculate_costs(self, full_sheet_cost: float, price_per_kg: float = 0.0,
                        thickness_mm: float = 1.0, material_density: float = 7.85) -> None:
        """
        Oblicz koszty materiału dla wszystkich arkuszy.
        """
        self.sheet_cost = full_sheet_cost
        self.total_cost = 0.0
        self.total_parts_area = 0.0
        self.used_sheet_area = 0.0
        
        full_sheet_area = self.sheet_width * self.sheet_height
        
        for sheet in self.sheets:
            sheet.sheet_cost = full_sheet_cost
            
            # Oblicz wagę każdego detalu
            for part in sheet.placed_parts:
                if part.weight_kg <= 0 and part.contour_area > 0:
                    area_cm2 = part.contour_area / 100
                    thickness_cm = thickness_mm / 10
                    mass_g = area_cm2 * thickness_cm * material_density
                    part.weight_kg = mass_g / 1000
            
            # Efektywne pole arkusza
            sheet.used_sheet_area = sheet.sheet_width * sheet.used_height
            
            # Koszt użytej części
            if price_per_kg > 0:
                used_area_cm2 = sheet.used_sheet_area / 100
                thickness_cm = thickness_mm / 10
                used_weight_kg = (used_area_cm2 * thickness_cm * material_density) / 1000
                sheet.used_sheet_cost = used_weight_kg * price_per_kg
            else:
                if full_sheet_area > 0:
                    sheet.used_sheet_cost = full_sheet_cost * (sheet.used_sheet_area / full_sheet_area)
                else:
                    sheet.used_sheet_cost = full_sheet_cost
            
            # Suma pól detali na arkuszu
            sheet.total_parts_area = sum(p.contour_area for p in sheet.placed_parts)
            
            # Efektywność arkusza
            if sheet.used_sheet_area > 0:
                sheet.efficiency = sheet.total_parts_area / sheet.used_sheet_area
            
            # Przypisz koszt do każdego detalu
            if sheet.total_parts_area > 0:
                for part in sheet.placed_parts:
                    share = part.contour_area / sheet.total_parts_area
                    part.material_cost = sheet.used_sheet_cost * share
            
            # Akumuluj globalne
            self.total_cost += sheet.used_sheet_cost
            self.total_parts_area += sheet.total_parts_area
            self.used_sheet_area += sheet.used_sheet_area
        
        self.used_sheet_cost = self.total_cost
        
        # Efektywna utylizacja globalna
        if self.used_sheet_area > 0:
            self.effective_utilization = self.total_parts_area / self.used_sheet_area
        
        self._calculate_breakdown()
    
    def _calculate_breakdown(self) -> None:
        """Oblicz podział kosztów per typ detalu"""
        self.cost_breakdown.clear()
        
        groups: Dict[str, List[NestedPart]] = {}
        for part in self.placed_parts:
            key = part.source_part_name or part.name
            if key not in groups:
                groups[key] = []
            groups[key].append(part)
        
        for part_name, parts in groups.items():
            if not parts:
                continue
            
            quantity = len(parts)
            unit_area = parts[0].contour_area
            unit_weight = parts[0].weight_kg
            total_area = sum(p.contour_area for p in parts)
            total_weight = sum(p.weight_kg for p in parts)
            total_cost = sum(p.material_cost for p in parts)
            
            share = total_area / self.total_parts_area if self.total_parts_area > 0 else 0
            
            breakdown = PartCostBreakdown(
                part_name=part_name,
                quantity=quantity,
                unit_weight_kg=unit_weight,
                total_weight_kg=total_weight,
                unit_contour_area=unit_area,
                total_contour_area=total_area,
                share_of_used_area=share,
                unit_material_cost=total_cost / quantity if quantity > 0 else 0,
                total_material_cost=total_cost
            )
            self.cost_breakdown.append(breakdown)
        
        self.cost_breakdown.sort(key=lambda x: x.share_of_used_area, reverse=True)


class FastNester:
    """
    Szybki nester oparty na rectpack.
    Używa bounding box do pakowania, przechowuje prawdziwe kształty.
    Obsługuje WIELE ARKUSZY automatycznie.
    """
    
    def __init__(self, sheet_width: float, sheet_height: float, spacing: float = 5.0,
                 max_sheets: int = 100):
        self.sheet_width = sheet_width
        self.sheet_height = sheet_height
        self.spacing = spacing
        self.max_sheets = max_sheets
        
        self.parts: List[dict] = []
        self.result: Optional[NestingResult] = None
        
        self.stop_flag = threading.Event()
        self._progress_callback: Optional[Callable] = None
    
    def add_part(self, dxf_part: Any, quantity: int = 1) -> None:
        """Dodaj detal do nestingu."""
        normalized = dxf_part.get_normalized_contour() if hasattr(dxf_part, 'get_normalized_contour') else []
        
        normalized_holes = []
        if hasattr(dxf_part, 'holes'):
            for hole in dxf_part.holes:
                norm_hole = [(x - dxf_part.min_x, y - dxf_part.min_y) for x, y in hole]
                normalized_holes.append(norm_hole)
        
        contour_area = dxf_part.contour_area if hasattr(dxf_part, 'contour_area') else dxf_part.width * dxf_part.height
        weight_kg = dxf_part.weight_kg if hasattr(dxf_part, 'weight_kg') else 0.0
        
        for i in range(quantity):
            self.parts.append({
                'name': dxf_part.name,
                'width': dxf_part.width + self.spacing,
                'height': dxf_part.height + self.spacing,
                'contour': normalized,
                'holes': normalized_holes,
                'area': (dxf_part.width + self.spacing) * (dxf_part.height + self.spacing),
                'contour_area': contour_area,
                'weight_kg': weight_kg,
                'source_name': dxf_part.name,
                'part_index': i
            })
    
    def add_part_from_dict(self, part_dict: dict, quantity: int = 1) -> None:
        """Dodaj detal ze słownika (dla integracji z GUI)."""
        width = part_dict.get('width', 100)
        height = part_dict.get('height', 100)
        contour = part_dict.get('contour', [])
        
        if not contour:
            contour = [(0, 0), (width, 0), (width, height), (0, height)]
        
        contour_area = part_dict.get('contour_area', width * height)
        
        for i in range(quantity):
            self.parts.append({
                'name': part_dict.get('name', 'Part'),
                'width': width + self.spacing,
                'height': height + self.spacing,
                'contour': contour,
                'holes': part_dict.get('holes', []),
                'area': (width + self.spacing) * (height + self.spacing),
                'contour_area': contour_area,
                'weight_kg': part_dict.get('weight_kg', 0.0),
                'source_name': part_dict.get('name', 'Part'),
                'part_index': i
            })
    
    def run_nesting(self, callback: Optional[Callable] = None,
                     deep_analysis: bool = False) -> NestingResult:
        """Uruchom nesting z obsługą wielu arkuszy."""
        if not HAS_RECTPACK:
            logger.error("rectpack not installed")
            return NestingResult()
        
        if not self.parts:
            return NestingResult()
        
        self.stop_flag.clear()
        self._progress_callback = callback
        
        # Sortuj detale od największych
        parts_sorted = sorted(self.parts, key=lambda x: x['area'], reverse=True)
        
        # Sprawdź które detale są za duże na arkusz
        max_part_width = self.sheet_width - self.spacing
        max_part_height = self.sheet_height - self.spacing
        
        fittable_parts = []
        unplaceable_parts = []
        
        for p in parts_sorted:
            p_w = p['width'] - self.spacing
            p_h = p['height'] - self.spacing
            
            # Sprawdź czy mieści się (także po obrocie)
            fits_normal = p_w <= max_part_width and p_h <= max_part_height
            fits_rotated = p_h <= max_part_width and p_w <= max_part_height
            
            if fits_normal or fits_rotated:
                fittable_parts.append(p)
            else:
                unplaceable_parts.append(UnplacedPart(
                    name=p['name'],
                    width=p_w,
                    height=p_h,
                    contour_area=p.get('contour_area', p_w * p_h),
                    reason=f"Za duży ({p_w:.0f}x{p_h:.0f}mm > arkusz {max_part_width:.0f}x{max_part_height:.0f}mm)",
                    source_part_name=p.get('source_name', p['name']),
                    part_index=p.get('part_index', 0)
                ))
        
        if deep_analysis:
            result = self._run_deep_analysis_multisheet(fittable_parts, callback)
        else:
            result = self._run_fast_multisheet(fittable_parts, callback)
        
        # Dodaj nieumieszczalne detale
        result.unplaced_parts = unplaceable_parts
        result.unplaced_count = len(unplaceable_parts)
        
        result.sheet_width = self.sheet_width
        result.sheet_height = self.sheet_height
        
        # Ustaw kompatybilność wsteczną (pierwszy arkusz)
        if result.sheets:
            first = result.sheets[0]
            result.used_width = first.used_width
            result.used_height = first.used_height
            result.efficiency = first.efficiency
        
        self.result = result
        return result
    
    def _run_fast_multisheet(self, parts: List[dict], callback: Optional[Callable]) -> NestingResult:
        """Szybki tryb z wieloma arkuszami"""
        logger.debug(f"→ Nesting FAST MULTI-SHEET: {len(parts)} parts...")
        start_time = time.time()
        
        result = NestingResult()
        remaining_parts = parts.copy()
        sheet_index = 0
        
        while remaining_parts and sheet_index < self.max_sheets:
            if self.stop_flag.is_set():
                break
            
            # Pakuj na jeden arkusz
            sheet_result, placed_indices = self._pack_single_sheet(
                remaining_parts, sheet_index
            )
            
            if not sheet_result.placed_parts:
                # Nie udało się umieścić nic więcej
                break
            
            result.sheets.append(sheet_result)
            result.placed_parts.extend(sheet_result.placed_parts)
            
            # Usuń umieszczone detale
            remaining_parts = [p for i, p in enumerate(remaining_parts) if i not in placed_indices]
            
            sheet_index += 1
            
            # Callback z postępem
            if callback:
                total_placed = len(result.placed_parts)
                total_parts = len(parts)
                efficiency = total_placed / total_parts if total_parts > 0 else 0
                callback(result.placed_parts, efficiency)
        
        # Dodaj pozostałe jako nieumieszczone
        for p in remaining_parts:
            result.unplaced_parts.append(UnplacedPart(
                name=p['name'],
                width=p['width'] - self.spacing,
                height=p['height'] - self.spacing,
                contour_area=p.get('contour_area', 0),
                reason="Brak miejsca na arkuszach",
                source_part_name=p.get('source_name', p['name']),
                part_index=p.get('part_index', 0)
            ))
        
        result.sheets_used = len(result.sheets)
        result.unplaced_count = len(result.unplaced_parts)
        
        # Oblicz globalną efektywność
        if result.sheets:
            total_parts_area = sum(s.total_parts_area for s in result.sheets)
            total_used_area = sum(s.used_sheet_area for s in result.sheets)
            result.total_efficiency = total_parts_area / total_used_area if total_used_area > 0 else 0
        
        elapsed = time.time() - start_time
        logger.debug(f"→ Completed in {elapsed:.1f}s | {result.sheets_used} sheets, {len(result.placed_parts)} placed")
        
        return result
    
    def _run_deep_analysis_multisheet(self, parts: List[dict], callback: Optional[Callable]) -> NestingResult:
        """Głęboka analiza z wieloma arkuszami"""
        logger.info(f"→ Nesting DEEP ANALYSIS MULTI-SHEET: {len(parts)} parts...")
        start_time = time.time()
        
        result = NestingResult()
        remaining_parts = parts.copy()
        sheet_index = 0
        
        while remaining_parts and sheet_index < self.max_sheets:
            if self.stop_flag.is_set():
                break
            
            # Głęboka analiza dla jednego arkusza
            sheet_result, placed_indices = self._pack_single_sheet_deep(
                remaining_parts, sheet_index
            )
            
            if not sheet_result.placed_parts:
                break
            
            result.sheets.append(sheet_result)
            result.placed_parts.extend(sheet_result.placed_parts)
            
            remaining_parts = [p for i, p in enumerate(remaining_parts) if i not in placed_indices]
            
            sheet_index += 1
            
            if callback:
                total_placed = len(result.placed_parts)
                total_parts = len(parts)
                efficiency = total_placed / total_parts if total_parts > 0 else 0
                callback(result.placed_parts, efficiency)
        
        for p in remaining_parts:
            result.unplaced_parts.append(UnplacedPart(
                name=p['name'],
                width=p['width'] - self.spacing,
                height=p['height'] - self.spacing,
                contour_area=p.get('contour_area', 0),
                reason="Brak miejsca na arkuszach",
                source_part_name=p.get('source_name', p['name']),
                part_index=p.get('part_index', 0)
            ))
        
        result.sheets_used = len(result.sheets)
        result.unplaced_count = len(result.unplaced_parts)
        
        if result.sheets:
            total_parts_area = sum(s.total_parts_area for s in result.sheets)
            total_used_area = sum(s.used_sheet_area for s in result.sheets)
            result.total_efficiency = total_parts_area / total_used_area if total_used_area > 0 else 0
        
        elapsed = time.time() - start_time
        logger.info(f"→ Deep analysis: {result.sheets_used} sheets in {elapsed:.1f}s")
        
        return result
    
    def _pack_single_sheet(self, parts: List[dict], sheet_index: int) -> Tuple[SheetResult, set]:
        """Pakuj detale na jeden arkusz (tryb szybki)"""
        best_result = None
        best_placed_indices = set()
        best_efficiency = 0.0
        
        for attempt in range(3):
            if self.stop_flag.is_set():
                break
            
            current_parts = parts.copy()
            if attempt > 0:
                fixed_count = max(1, len(current_parts) // 3)
                fixed = current_parts[:fixed_count]
                rest = current_parts[fixed_count:]
                random.shuffle(rest)
                current_parts = fixed + rest
            
            sheet, placed_indices, efficiency = self._try_packing_sheet(
                current_parts, sheet_index,
                rectpack.MaxRectsBssf,
                rectpack.SORT_AREA
            )
            
            if efficiency > best_efficiency:
                best_efficiency = efficiency
                best_result = sheet
                best_placed_indices = placed_indices
        
        return best_result or SheetResult(sheet_index=sheet_index), best_placed_indices
    
    def _pack_single_sheet_deep(self, parts: List[dict], sheet_index: int) -> Tuple[SheetResult, set]:
        """Pakuj detale na jeden arkusz (tryb głęboki)"""
        best_result = None
        best_placed_indices = set()
        best_efficiency = 0.0
        best_algo = None
        best_sort = None
        
        # Faza 1: Wszystkie kombinacje
        for pack_algo in PACKING_ALGORITHMS:
            if self.stop_flag.is_set():
                break
            for sort_algo in SORT_ALGORITHMS:
                if self.stop_flag.is_set():
                    break
                
                sheet, placed_indices, efficiency = self._try_packing_sheet(
                    parts, sheet_index, pack_algo, sort_algo
                )
                
                if efficiency > best_efficiency:
                    best_efficiency = efficiency
                    best_result = sheet
                    best_placed_indices = placed_indices
                    best_algo = pack_algo
                    best_sort = sort_algo
        
        # Faza 2: Tasowanie z najlepszym
        if best_algo and not self.stop_flag.is_set():
            for i in range(30):
                if self.stop_flag.is_set():
                    break
                
                shuffled = parts.copy()
                random.shuffle(shuffled)
                
                sheet, placed_indices, efficiency = self._try_packing_sheet(
                    shuffled, sheet_index, best_algo, best_sort
                )
                
                if efficiency > best_efficiency:
                    best_efficiency = efficiency
                    best_result = sheet
                    best_placed_indices = placed_indices
        
        return best_result or SheetResult(sheet_index=sheet_index), best_placed_indices
    
    def _try_packing_sheet(self, parts: List[dict], sheet_index: int,
                            pack_algo, sort_algo) -> Tuple[SheetResult, set, float]:
        """Wykonaj jedną próbę pakowania na arkusz"""
        packer = rectpack.newPacker(
            mode=rectpack.PackingMode.Offline,
            pack_algo=pack_algo,
            rotation=True,
            sort_algo=sort_algo
        )
        
        packer.add_bin(self.sheet_width, self.sheet_height)
        
        for i, p in enumerate(parts):
            packer.add_rect(p['width'], p['height'], rid=i)
        
        packer.pack()
        
        placed = []
        placed_indices = set()
        total_area = 0
        total_contour_area = 0
        max_x = 0
        max_y = 0
        
        for abin in packer:
            for rect in abin:
                orig = parts[rect.rid]
                placed_indices.add(rect.rid)
                
                rotated = abs(rect.width - orig['width']) > 0.1
                
                orig_w = orig['width'] - self.spacing
                orig_h = orig['height'] - self.spacing
                
                if rotated:
                    placed_width = orig_h
                    placed_height = orig_w
                    rotation = 90.0
                else:
                    placed_width = orig_w
                    placed_height = orig_h
                    rotation = 0.0
                
                nested = NestedPart(
                    name=orig['name'],
                    x=rect.x,
                    y=rect.y,
                    width=placed_width,
                    height=placed_height,
                    rotation=rotation,
                    original_contour=orig['contour'],
                    holes=orig['holes'],
                    orig_width=orig_w,
                    orig_height=orig_h,
                    contour_area=orig.get('contour_area', orig_w * orig_h),
                    weight_kg=orig.get('weight_kg', 0.0),
                    source_part_name=orig.get('source_name', orig['name']),
                    part_index=orig.get('part_index', 0),
                    sheet_index=sheet_index
                )
                placed.append(nested)
                
                total_area += orig['area']
                total_contour_area += orig.get('contour_area', orig_w * orig_h)
                max_x = max(max_x, rect.x + rect.width)
                max_y = max(max_y, rect.y + rect.height)
        
        efficiency = total_area / (max_x * max_y) if max_x > 0 and max_y > 0 else 0
        
        sheet = SheetResult(
            sheet_index=sheet_index,
            placed_parts=placed,
            sheet_width=self.sheet_width,
            sheet_height=self.sheet_height,
            used_width=max_x,
            used_height=max_y,
            total_parts_area=total_contour_area,
            used_sheet_area=self.sheet_width * max_y if max_y > 0 else 0,
            efficiency=efficiency
        )
        
        return sheet, placed_indices, efficiency
    
    def stop(self) -> None:
        """Zatrzymaj nesting"""
        self.stop_flag.set()
    
    def export_dxf(self, filepath: str, sheet_index: int = 0) -> bool:
        """Eksportuj wynik do DXF (pojedynczy arkusz)"""
        if not self.result or not self.result.sheets:
            return False
        
        if sheet_index >= len(self.result.sheets):
            return False
        
        sheet = self.result.sheets[sheet_index]
        
        try:
            import ezdxf
        except ImportError:
            logger.error("ezdxf not installed")
            return False
        
        doc = ezdxf.new()
        msp = doc.modelspace()
        
        # Ramka arkusza
        msp.add_lwpolyline([
            (0, 0),
            (self.sheet_width, 0),
            (self.sheet_width, self.sheet_height),
            (0, self.sheet_height)
        ], close=True, dxfattribs={'color': 7})
        
        # Linia użytej wysokości
        msp.add_line(
            (0, sheet.used_height),
            (self.sheet_width, sheet.used_height),
            dxfattribs={'color': 1}
        )
        
        # Detale
        for part in sheet.placed_parts:
            contour = part.get_placed_contour()
            if len(contour) >= 3:
                msp.add_lwpolyline(contour, close=True, dxfattribs={'color': 3})
            
            for hole in part.get_placed_holes():
                if len(hole) >= 3:
                    msp.add_lwpolyline(hole, close=True, dxfattribs={'color': 1})
        
        doc.saveas(filepath)
        logger.info(f"Saved: {filepath}")
        return True
    
    def export_all_dxf(self, base_filepath: str) -> List[str]:
        """Eksportuj wszystkie arkusze do DXF"""
        if not self.result or not self.result.sheets:
            return []
        
        saved_files = []
        base, ext = base_filepath.rsplit('.', 1) if '.' in base_filepath else (base_filepath, 'dxf')
        
        for i, sheet in enumerate(self.result.sheets):
            if len(self.result.sheets) == 1:
                filepath = f"{base}.{ext}"
            else:
                filepath = f"{base}_sheet{i+1}.{ext}"
            
            if self.export_dxf(filepath, i):
                saved_files.append(filepath)
        
        return saved_files
    
    def clear(self) -> None:
        """Wyczyść listę detali"""
        self.parts.clear()
        self.result = None


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":
    print("FastNester Multi-Sheet Test")
    print("=" * 40)
    
    # Mały arkusz żeby wymusić wiele arkuszy
    nester = FastNester(800, 600, spacing=5.0)
    
    class MockPart:
        def __init__(self, name, w, h):
            self.name = name
            self.width = w
            self.height = h
            self.min_x = 0
            self.min_y = 0
            self.holes = []
            self.contour_area = w * h * 0.9
            self.weight_kg = w * h * 0.001 * 7.85 / 1000
        
        def get_normalized_contour(self):
            return [(0, 0), (self.width, 0), (self.width, self.height), (0, self.height)]
    
    parts = [
        MockPart("Płyta_A", 300, 200),
        MockPart("Płyta_B", 250, 180),
        MockPart("Płyta_C", 200, 150),
        MockPart("ZaDuży", 1000, 1000),  # Za duży
    ]
    
    for p in parts:
        nester.add_part(p, quantity=5)
    
    result = nester.run_nesting()
    
    print(f"\nWynik:")
    print(f"  Arkusze użyte: {result.sheets_used}")
    print(f"  Umieszczono: {len(result.placed_parts)}")
    print(f"  Nieumieszczone: {result.unplaced_count}")
    
    for i, sheet in enumerate(result.sheets):
        print(f"\n  Arkusz #{i+1}:")
        print(f"    Detali: {len(sheet.placed_parts)}")
        print(f"    Efektywność: {sheet.efficiency:.1%}")
        print(f"    Użyte: {sheet.used_width:.0f}x{sheet.used_height:.0f}mm")
    
    if result.unplaced_parts:
        print(f"\n  Nieumieszczone detale:")
        for up in result.unplaced_parts:
            print(f"    - {up.name}: {up.reason}")
