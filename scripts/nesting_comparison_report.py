#!/usr/bin/env python3
"""
Kompleksowy skrypt porownujacy NewERP vs CypNest z nestingiem i wizualizacja.

Funkcje:
- Odczyt danych referencyjnych z CypNest XLSX
- Nesting (pakietowanie) detali z DXF
- Wizualizacja arkuszy i detali
- Kalkulacja czasow z dynamika maszyny
- Porownanie wynikow z CypNest
- Generacja raportu HTML z grafikami
"""

import argparse
import base64
import io
import json
import math
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

# Import UnifiedDXFReader dla poprawnego odczytu konturów
try:
    from core.dxf import UnifiedDXFReader
    HAS_UNIFIED_READER = True
except ImportError:
    HAS_UNIFIED_READER = False

try:
    import pandas as pd
    import ezdxf
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import Polygon as MplPolygon, Rectangle, Circle
    from matplotlib.collections import PatchCollection
    import numpy as np
except ImportError as e:
    print(f"Brak wymaganej biblioteki: {e}")
    print("Zainstaluj: pip install pandas openpyxl ezdxf matplotlib numpy")
    sys.exit(1)

# Machine dynamics constants
RAPID_SPEED_M_MIN = 120.0
ACCELERATION_M_S2 = 10.0
HEAD_LIFT_TIME_S = 0.1
MIN_MOVE_TIME_S = 0.05


@dataclass
class ContourData:
    """Kontur detalu"""
    points: List[Tuple[float, float]]
    perimeter_mm: float = 0
    area_mm2: float = 0
    is_hole: bool = False
    centroid: Tuple[float, float] = (0, 0)


@dataclass
class PartData:
    """Dane detalu"""
    name: str
    dxf_path: str = ""
    qty: int = 1
    material: str = "1.4301"
    thickness_mm: float = 2.0

    # Geometry
    width_mm: float = 0
    height_mm: float = 0
    contour_area_mm2: float = 0
    bbox_area_mm2: float = 0
    outer_contour: List[Tuple[float, float]] = field(default_factory=list)
    holes: List[List[Tuple[float, float]]] = field(default_factory=list)

    # Cutting
    cut_length_mm: float = 0
    lead_in_length_mm: float = 0
    pierce_count: int = 0

    # Timing
    cut_time_s: float = 0
    lead_in_time_s: float = 0
    pierce_time_s: float = 0
    rapid_time_s: float = 0
    total_time_s: float = 0


@dataclass
class SheetLayout:
    """Uklad detali na arkuszu"""
    sheet_index: int = 0
    width_mm: float = 0
    height_mm: float = 0
    used_width_mm: float = 0
    used_height_mm: float = 0
    parts: List[Tuple[PartData, float, float, float]] = field(default_factory=list)  # (part, x, y, rot)
    utilization_pct: float = 0

    # Material info
    material: str = ""
    thickness: float = 0

    # Timing for sheet
    total_cut_time_s: float = 0
    total_rapid_time_s: float = 0  # Between parts


@dataclass
class CypNestReference:
    """Dane referencyjne z CypNest"""
    source_file: str
    material: str = ""
    thickness_mm: float = 0
    total_cut_length_m: float = 0
    total_cut_time_s: float = 0
    sheets_count: int = 0
    parts: List[Dict] = field(default_factory=list)


@dataclass
class ComparisonResult:
    """Wynik porownania"""
    folder: str
    newerp_cut_length_m: float = 0
    cypnest_cut_length_m: float = 0
    cut_length_diff_pct: float = 0
    newerp_time_s: float = 0
    cypnest_time_s: float = 0
    time_diff_pct: float = 0
    sheets: List[SheetLayout] = field(default_factory=list)
    parts: List[PartData] = field(default_factory=list)
    status: str = "OK"


class DynamicCalculator:
    """Kalkulator z dynamika maszyny"""

    def __init__(self):
        self.cutting_speeds = {}
        self.pierce_times = {}
        self._load_rates()

    def _load_rates(self):
        """Zaladuj stawki z Supabase"""
        try:
            from core.supabase_client import get_supabase_client
            client = get_supabase_client()

            result = client.table('current_cutting_prices').select('*').execute()
            for row in result.data:
                key = (row['material'], row['thickness'])
                self.cutting_speeds[key] = row['cutting_speed']

            result = client.table('current_piercing_rates').select('*').execute()
            for row in result.data:
                mat_map = {'stainless': '1.4301', 'carbon': 'S235', 'aluminum': 'AL'}
                material = mat_map.get(row['material_type'], row['material_type'])
                key = (material, row['thickness'])
                self.pierce_times[key] = row['pierce_time_s']

            print(f"  Zaladowano {len(self.cutting_speeds)} stawek ciecia")
        except Exception as e:
            print(f"  Stawki domyslne (brak Supabase): {e}")
            self._set_defaults()

    def _set_defaults(self):
        """Domyslne stawki"""
        for t in [1, 1.5, 2, 3, 4, 5, 6, 8, 10, 12]:
            self.cutting_speeds[('1.4301', t)] = max(1, 20 - t * 1.5)
            self.cutting_speeds[('S235', t)] = max(1, 25 - t * 1.5)
            self.cutting_speeds[('ST42CrMo4', t)] = max(1, 22 - t * 1.5)
            self.pierce_times[('1.4301', t)] = 0.5 + t * 0.1
            self.pierce_times[('S235', t)] = 0.3 + t * 0.08
            self.pierce_times[('ST42CrMo4', t)] = 0.4 + t * 0.09

    def get_cutting_speed(self, material: str, thickness: float) -> float:
        """Predkosc ciecia m/min"""
        key = (material, thickness)
        if key in self.cutting_speeds:
            return self.cutting_speeds[key]
        # Szukaj najblizszej grubosci
        for k in self.cutting_speeds:
            if k[0] == material and abs(k[1] - thickness) < 1:
                return self.cutting_speeds[k]
        return 10.0

    def get_pierce_time(self, material: str, thickness: float) -> float:
        """Czas przebicia (s)"""
        key = (material, thickness)
        if key in self.pierce_times:
            return self.pierce_times[key]
        return 0.5 + thickness * 0.1

    def calc_rapid_time(self, distance_mm: float) -> float:
        """Czas ruchu jalowego z dynamika"""
        if distance_mm <= 0:
            return 0

        distance_m = distance_mm / 1000
        v_max = RAPID_SPEED_M_MIN / 60
        a = ACCELERATION_M_S2
        accel_dist = v_max**2 / (2 * a)

        if distance_m < 2 * accel_dist:
            move_time = 2 * math.sqrt(distance_m / a)
        else:
            accel_time = v_max / a
            cruise_dist = distance_m - 2 * accel_dist
            cruise_time = cruise_dist / v_max
            move_time = 2 * accel_time + cruise_time

        return max(move_time + 2 * HEAD_LIFT_TIME_S, MIN_MOVE_TIME_S)


def parse_cypnest_xlsx(xlsx_path: Path) -> Optional[CypNestReference]:
    """Parsuj XLSX z CypNest"""
    try:
        xl = pd.ExcelFile(xlsx_path)
        data = CypNestReference(source_file=xlsx_path.name)

        if 'All Parts List' in xl.sheet_names:
            df = pd.read_excel(xlsx_path, sheet_name='All Parts List', header=1)

            for _, row in df.iterrows():
                name = str(row.get('Part Name', ''))
                if not name or pd.isna(name) or name == 'nan':
                    continue

                qty_val = row.get('Qty', 1)
                qty = int(float(str(qty_val).replace(' ', '').split('/')[0].strip()) or 1) if not pd.isna(qty_val) else 1

                cut_val = row.get('Cut Length(m)', 0)
                cut_length = float(cut_val) if not pd.isna(cut_val) else 0

                size_str = str(row.get('Part Size(mm*mm)', '0 * 0'))
                width, height = 0, 0
                if '*' in size_str:
                    parts = size_str.split('*')
                    width = float(parts[0].strip())
                    height = float(parts[1].strip())

                data.parts.append({
                    'name': name, 'qty': qty, 'cut_length_m': cut_length,
                    'width': width, 'height': height
                })
                data.total_cut_length_m += cut_length * qty

        # Parsuj czas z Result sheets
        result_sheets = [s for s in xl.sheet_names if s.startswith('Result')]
        data.sheets_count = len(result_sheets)

        for sheet_name in result_sheets:
            df = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=None)
            for i in range(min(20, len(df))):
                for j in range(min(10, len(df.columns))):
                    val = df.iloc[i, j]
                    if pd.isna(val):
                        continue
                    val_str = str(val)

                    # Czas ciecia (np. "1min10s", "59s")
                    if 'min' in val_str.lower() or (val_str.endswith('s') and 's' in val_str):
                        try:
                            time_s = parse_time_string(val_str)
                            if time_s > 0:
                                data.total_cut_time_s += time_s
                        except:
                            pass

                    # Material
                    if '1.4301' in val_str:
                        data.material = '1.4301'
                    elif 'S235' in val_str:
                        data.material = 'S235'
                    elif 'ST42' in val_str:
                        data.material = 'ST42CrMo4'

                    # Grubosc
                    if data.thickness_mm == 0:
                        try:
                            t = float(val_str.replace(',', '.'))
                            if 0.5 <= t <= 20:
                                data.thickness_mm = t
                        except:
                            pass

        return data
    except Exception as e:
        print(f"  Blad parsowania {xlsx_path.name}: {e}")
        return None


def parse_time_string(time_str: str) -> float:
    """Parsuj czas z formatu CypNest (np. '1min10s', '59s')"""
    time_str = time_str.lower().strip()
    total_s = 0

    if 'min' in time_str:
        parts = time_str.split('min')
        mins = float(parts[0].strip())
        total_s += mins * 60
        if len(parts) > 1 and 's' in parts[1]:
            secs = float(parts[1].replace('s', '').strip() or 0)
            total_s += secs
    elif time_str.endswith('s'):
        total_s = float(time_str.replace('s', '').strip())

    return total_s


def analyze_dxf(filepath: Path, calculator: DynamicCalculator) -> Optional[PartData]:
    """
    Analizuj DXF i oblicz parametry ciecia.

    UWAGA: Używa UnifiedDXFReader dla poprawnego budowania konturów z LINE+ARC.
    """
    try:
        # === NOWA METODA: UnifiedDXFReader ===
        if HAS_UNIFIED_READER:
            reader = UnifiedDXFReader()
            dxf_part = reader.read(str(filepath))

            if not dxf_part:
                print(f"  UnifiedDXFReader failed for {filepath.name}")
                return None

            # Konwertuj DXFPart na PartData
            part = PartData(
                name=dxf_part.name,
                dxf_path=str(filepath),
                qty=dxf_part.quantity,
                material=dxf_part.material or '1.4301',
                thickness_mm=dxf_part.thickness or 2.0,
                width_mm=dxf_part.width,
                height_mm=dxf_part.height,
                contour_area_mm2=dxf_part.contour_area,
                bbox_area_mm2=dxf_part.bounding_area,
                cut_length_mm=dxf_part.cut_length_mm,
                pierce_count=dxf_part.pierce_count,
            )

            # Kontur zewnetrzny (znormalizowany)
            if dxf_part.outer_contour:
                part.outer_contour = dxf_part.get_normalized_contour()

            # Otwory (znormalizowane)
            part.holes = dxf_part.get_normalized_holes()

            # Oblicz czasy
            thickness = part.thickness_mm
            material = part.material

            part.lead_in_length_mm = thickness * part.pierce_count

            speed_m_min = calculator.get_cutting_speed(material, thickness)
            speed_mm_s = speed_m_min * 1000 / 60

            part.cut_time_s = part.cut_length_mm / speed_mm_s if speed_mm_s > 0 else 0
            part.lead_in_time_s = part.lead_in_length_mm / speed_mm_s if speed_mm_s > 0 else 0
            part.pierce_time_s = calculator.get_pierce_time(material, thickness) * part.pierce_count

            # Rapid miedzy konturami (szacunkowo)
            if part.pierce_count > 1:
                # Przybliżona odległość rapid między otworami
                avg_rapid_dist = (part.width_mm + part.height_mm) / 2
                part.rapid_time_s = calculator.calc_rapid_time(avg_rapid_dist * (part.pierce_count - 1) / 2)

            part.total_time_s = part.cut_time_s + part.lead_in_time_s + part.pierce_time_s + part.rapid_time_s

            return part

        # === FALLBACK: Stara metoda (dla kompatybilności) ===
        return _analyze_dxf_legacy(filepath, calculator)

    except Exception as e:
        print(f"  Blad DXF {filepath.name}: {e}")
        import traceback
        traceback.print_exc()
        return None


def _analyze_dxf_legacy(filepath: Path, calculator: DynamicCalculator) -> Optional[PartData]:
    """Stara metoda analizy DXF (fallback gdy UnifiedDXFReader niedostępny)"""
    try:
        doc = ezdxf.readfile(str(filepath))
        msp = doc.modelspace()

        # Parsuj nazwe
        name = filepath.stem
        thickness = 2.0
        material = '1.4301'
        qty = 1

        import re
        name_lower = name.lower()

        # Parse #XXmm format first (e.g. #12mm)
        hash_match = re.search(r'#(\d+(?:[.,]\d+)?)\s*mm', name, re.IGNORECASE)
        if hash_match:
            try:
                t = float(hash_match.group(1).replace(',', '.'))
                if 0.5 <= t <= 30:
                    thickness = t
            except:
                pass

        # Parse XXmm format
        for p in name.replace('-', '_').split('_'):
            p_l = p.lower()
            if 'szt' in p_l:
                try:
                    qty = int(p_l.replace('szt', '').strip())
                except:
                    pass
            if 'mm' in p_l and thickness == 2.0:
                try:
                    t = float(p_l.replace('mm', '').replace(',', '.').replace('#', '').strip())
                    if 0.5 <= t <= 30:
                        thickness = t
                except:
                    pass

        if '1.4301' in name_lower or 'inox' in name_lower or '4301' in name_lower:
            material = '1.4301'
        elif 's235' in name_lower or '_fe_' in name_lower:
            material = 'S235'
        elif 'st42' in name_lower or '42crmo4' in name_lower:
            material = '42CRM04'

        part = PartData(
            name=name, dxf_path=str(filepath), qty=qty,
            material=material, thickness_mm=thickness
        )

        # Zbierz geometrie (stara metoda - każda entity osobno)
        IGNORE_LAYERS = {
            'AM_', 'RAMKA', 'WYMIARY', 'DIM', 'TEXT', 'DEFPOINTS',
            'IV_ARC_CENTERS', 'BEND', 'FOLD', 'MARK', 'ENGRAV'
        }

        contours = []
        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = float('-inf'), float('-inf')

        for entity in msp:
            layer = entity.dxf.layer.upper()
            etype = entity.dxftype()

            if 'IV_FEATURE_PROFILES' in layer:
                if etype != 'ARC':
                    continue
            else:
                skip = False
                for ign in IGNORE_LAYERS:
                    if ign in layer or layer == ign or layer.startswith(ign):
                        skip = True
                        break
                if skip:
                    continue

            points, perimeter = extract_entity_geometry(entity, etype)

            if points and perimeter > 0:
                contours.append(ContourData(points=points, perimeter_mm=perimeter))
                for px, py in points:
                    min_x, max_x = min(min_x, px), max(max_x, px)
                    min_y, max_y = min(min_y, py), max(max_y, py)

        if not contours:
            return None

        part.width_mm = max_x - min_x
        part.height_mm = max_y - min_y
        part.bbox_area_mm2 = part.width_mm * part.height_mm

        max_area = 0
        outer_idx = 0
        for i, c in enumerate(contours):
            area = calc_polygon_area(c.points)
            c.area_mm2 = area
            if area > max_area:
                max_area = area
                outer_idx = i

        part.contour_area_mm2 = max_area

        if contours:
            part.outer_contour = [(p[0] - min_x, p[1] - min_y) for p in contours[outer_idx].points]
            for i, c in enumerate(contours):
                if i != outer_idx:
                    c.is_hole = True
                    part.holes.append([(p[0] - min_x, p[1] - min_y) for p in c.points])

        part.cut_length_mm = sum(c.perimeter_mm for c in contours)
        part.pierce_count = len(contours)
        part.lead_in_length_mm = thickness * part.pierce_count

        speed_m_min = calculator.get_cutting_speed(material, thickness)
        speed_mm_s = speed_m_min * 1000 / 60

        part.cut_time_s = part.cut_length_mm / speed_mm_s
        part.lead_in_time_s = part.lead_in_length_mm / speed_mm_s
        part.pierce_time_s = calculator.get_pierce_time(material, thickness) * part.pierce_count

        if len(contours) > 1:
            rapid_dist = estimate_rapid_distance(contours)
            part.rapid_time_s = calculator.calc_rapid_time(rapid_dist)

        part.total_time_s = part.cut_time_s + part.lead_in_time_s + part.pierce_time_s + part.rapid_time_s

        return part
    except Exception as e:
        print(f"  Blad DXF (legacy) {filepath.name}: {e}")
        return None


def extract_entity_geometry(entity, etype: str) -> Tuple[List[Tuple[float, float]], float]:
    """Wyodrebnij punkty i obwod z encji DXF"""
    points = []
    perimeter = 0

    if etype == 'CIRCLE':
        r = entity.dxf.radius
        cx, cy = entity.dxf.center.x, entity.dxf.center.y
        n = 36
        points = [(cx + r * math.cos(2 * math.pi * i / n),
                   cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
        perimeter = 2 * math.pi * r

    elif etype == 'ARC':
        r = entity.dxf.radius
        cx, cy = entity.dxf.center.x, entity.dxf.center.y
        sa, ea = math.radians(entity.dxf.start_angle), math.radians(entity.dxf.end_angle)
        if ea < sa:
            ea += 2 * math.pi
        n = max(10, int((ea - sa) / (math.pi/2) * 10))
        points = [(cx + r * math.cos(sa + (ea-sa)*i/n),
                   cy + r * math.sin(sa + (ea-sa)*i/n)) for i in range(n+1)]
        perimeter = r * (ea - sa)

    elif etype == 'LINE':
        p1 = (entity.dxf.start.x, entity.dxf.start.y)
        p2 = (entity.dxf.end.x, entity.dxf.end.y)
        points = [p1, p2]
        perimeter = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)

    elif etype == 'LWPOLYLINE':
        pts_bulge = list(entity.get_points('xyb'))
        points = [(p[0], p[1]) for p in pts_bulge]
        bulges = [p[2] if len(p) > 2 else 0 for p in pts_bulge]

        if points:
            is_closed = entity.closed
            n = len(points)
            for i in range(n if is_closed else n-1):
                p1, p2 = points[i], points[(i+1) % n]
                bulge = bulges[i] if i < len(bulges) else 0

                if bulge != 0:
                    chord = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
                    angle = 4 * math.atan(abs(bulge))
                    if angle > 0 and chord > 0:
                        r = chord / (2 * math.sin(angle/2))
                        perimeter += r * angle
                else:
                    perimeter += math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)

    elif etype == 'POLYLINE':
        try:
            vertices = list(entity.vertices)
            points = [(v.dxf.location.x, v.dxf.location.y) for v in vertices]
            bulges = [v.dxf.bulge if hasattr(v.dxf, 'bulge') else 0 for v in vertices]

            if points:
                is_closed = entity.is_closed
                n = len(points)
                for i in range(n if is_closed else n-1):
                    p1, p2 = points[i], points[(i+1) % n]
                    bulge = bulges[i] if i < len(bulges) else 0

                    if bulge != 0:
                        chord = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
                        angle = 4 * math.atan(abs(bulge))
                        if angle > 0 and chord > 0:
                            r = chord / (2 * math.sin(angle/2))
                            perimeter += r * angle
                    else:
                        perimeter += math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
        except:
            pass

    return points, perimeter


def calc_polygon_area(points: List[Tuple[float, float]]) -> float:
    """Oblicz pole wielokata (Shoelace)"""
    if len(points) < 3:
        return 0
    n = len(points)
    area = 0
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]
    return abs(area) / 2


def estimate_rapid_distance(contours: List[ContourData]) -> float:
    """Szacuj dystans ruchu jalowego miedzy konturami"""
    if len(contours) <= 1:
        return 0

    # Uzyj centroidow
    centroids = []
    for c in contours:
        if c.points:
            cx = sum(p[0] for p in c.points) / len(c.points)
            cy = sum(p[1] for p in c.points) / len(c.points)
            centroids.append((cx, cy))

    # Nearest neighbor
    total_dist = 0
    if centroids:
        current = centroids[0]
        visited = {0}
        for _ in range(len(centroids) - 1):
            best_dist = float('inf')
            best_idx = -1
            for i, c in enumerate(centroids):
                if i not in visited:
                    d = math.sqrt((c[0]-current[0])**2 + (c[1]-current[1])**2)
                    if d < best_dist:
                        best_dist = d
                        best_idx = i
            if best_idx >= 0:
                total_dist += best_dist
                current = centroids[best_idx]
                visited.add(best_idx)

    return total_dist


def calc_sheet_rapid_time(sheet: SheetLayout, calculator: DynamicCalculator) -> float:
    """Oblicz czas rapid miedzy czesciami na arkuszu"""
    if not sheet.parts or len(sheet.parts) <= 1:
        return 0

    # Zbierz centroidy wszystkich czesci na arkuszu
    centroids = []
    for part, x, y, rot in sheet.parts:
        # Centroid czesci
        w = part.height_mm if rot == 90 else part.width_mm
        h = part.width_mm if rot == 90 else part.height_mm
        cx = x + w / 2
        cy = y + h / 2
        centroids.append((cx, cy))

    # Nearest neighbor - oblicz sciezke rapid
    total_dist = 0
    current_pos = (0, 0)  # Start od rogu arkusza
    visited = set()

    for _ in range(len(centroids)):
        best_dist = float('inf')
        best_idx = -1
        for i, (cx, cy) in enumerate(centroids):
            if i not in visited:
                d = math.sqrt((cx - current_pos[0])**2 + (cy - current_pos[1])**2)
                if d < best_dist:
                    best_dist = d
                    best_idx = i

        if best_idx >= 0:
            total_dist += best_dist
            current_pos = centroids[best_idx]
            visited.add(best_idx)

    # Oblicz czas rapid
    return calculator.calc_rapid_time(total_dist)


def simple_nesting(parts: List[PartData], sheet_width: float, sheet_height: float, margin: float = 8.0) -> List[SheetLayout]:
    """Prosty nesting (bin packing)"""
    try:
        import rectpack
        has_rectpack = True
    except ImportError:
        has_rectpack = False

    sheets = []
    all_rects = []

    # Przygotuj prostokaty
    for part in parts:
        for i in range(part.qty):
            w = part.width_mm + 2*margin
            h = part.height_mm + 2*margin
            all_rects.append((w, h, part, i))

    if has_rectpack:
        packer = rectpack.newPacker(
            mode=rectpack.PackingMode.Offline,
            pack_algo=rectpack.MaxRectsBssf,
            rotation=True,
            sort_algo=rectpack.SORT_AREA
        )

        # Dodaj wiele binow (arkuszy)
        for i in range(20):  # Max 20 arkuszy
            packer.add_bin(sheet_width, sheet_height, bid=i)

        for idx, (w, h, part, pi) in enumerate(all_rects):
            packer.add_rect(w, h, rid=idx)

        packer.pack()

        # Zbierz wyniki - poprawne API rectpack
        sheets_data = {}
        for bid, abin in enumerate(packer):
            for rect in abin:
                if bid not in sheets_data:
                    sheets_data[bid] = SheetLayout(
                        sheet_index=bid, width_mm=sheet_width, height_mm=sheet_height
                    )

                rid = rect.rid
                x, y = rect.x, rect.y
                w_mm, h_mm, part, pi = all_rects[rid]

                # Sprawdz rotacje
                orig_w = part.width_mm + 2*margin
                rotation = 90 if abs(rect.width - orig_w) > 0.1 else 0

                sheets_data[bid].parts.append((
                    part, x + margin, y + margin, rotation
                ))

        sheets = list(sheets_data.values())

        # Oblicz wykorzystanie
        for sheet in sheets:
            if sheet.parts:
                max_x, max_y = 0, 0
                total_area = 0
                for part, x, y, rot in sheet.parts:
                    w = part.height_mm if rot == 90 else part.width_mm
                    h = part.width_mm if rot == 90 else part.height_mm
                    max_x = max(max_x, x + w)
                    max_y = max(max_y, y + h)
                    total_area += part.width_mm * part.height_mm

                sheet.used_width_mm = max_x
                sheet.used_height_mm = max_y
                used_area = max_x * max_y
                sheet.utilization_pct = (total_area / used_area * 100) if used_area > 0 else 0
    else:
        # Prosty fallback - jeden arkusz
        sheet = SheetLayout(sheet_index=0, width_mm=sheet_width, height_mm=sheet_height)
        y = margin
        x = margin
        row_height = 0

        for part in parts:
            for i in range(part.qty):
                if x + part.width_mm + margin > sheet_width:
                    x = margin
                    y += row_height + margin
                    row_height = 0

                if y + part.height_mm + margin > sheet_height:
                    sheets.append(sheet)
                    sheet = SheetLayout(sheet_index=len(sheets), width_mm=sheet_width, height_mm=sheet_height)
                    x, y = margin, margin
                    row_height = 0

                sheet.parts.append((part, x, y, 0))
                x += part.width_mm + margin
                row_height = max(row_height, part.height_mm)

        if sheet.parts:
            sheets.append(sheet)

    return sheets


def visualize_sheet(sheet: SheetLayout, output_path: Path = None) -> str:
    """Wizualizacja arkusza - zwraca base64 PNG"""
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    ax.set_aspect('equal')
    ax.set_facecolor('#1a1a1a')
    fig.patch.set_facecolor('#0f0f0f')

    # Arkusz
    ax.add_patch(Rectangle(
        (0, 0), sheet.width_mm, sheet.height_mm,
        fill=True, facecolor='#2d2d2d', edgecolor='#4a4a4a', linewidth=2
    ))

    # Uzyty obszar
    if sheet.used_width_mm and sheet.used_height_mm:
        ax.add_patch(Rectangle(
            (0, 0), sheet.used_width_mm, sheet.used_height_mm,
            fill=False, edgecolor='#f59e0b', linewidth=2, linestyle='--'
        ))

    # Detale
    colors = plt.cm.Set3(np.linspace(0, 1, max(1, len(sheet.parts))))

    for idx, (part, x, y, rot) in enumerate(sheet.parts):
        color = colors[idx % len(colors)]

        # Kontur
        if part.outer_contour:
            contour = part.outer_contour.copy()
            if rot == 90:
                contour = [(p[1], part.width_mm - p[0]) for p in contour]
            contour = [(p[0] + x, p[1] + y) for p in contour]

            poly = MplPolygon(contour, closed=True, facecolor=color,
                             edgecolor='#22c55e', linewidth=1.5, alpha=0.8)
            ax.add_patch(poly)

            # Otwory
            for hole in part.holes:
                h = hole.copy()
                if rot == 90:
                    h = [(p[1], part.width_mm - p[0]) for p in h]
                h = [(p[0] + x, p[1] + y) for p in h]
                hole_poly = MplPolygon(h, closed=True, facecolor='#1a1a1a',
                                       edgecolor='#ef4444', linewidth=1)
                ax.add_patch(hole_poly)
        else:
            # Bbox
            w = part.height_mm if rot == 90 else part.width_mm
            h = part.width_mm if rot == 90 else part.height_mm
            ax.add_patch(Rectangle(
                (x, y), w, h, facecolor=color, edgecolor='#22c55e', linewidth=1.5, alpha=0.8
            ))

        # Nazwa detalu
        w = part.height_mm if rot == 90 else part.width_mm
        h = part.width_mm if rot == 90 else part.height_mm
        label = part.name[:15] if len(part.name) > 15 else part.name
        ax.text(x + w/2, y + h/2, label, ha='center', va='center',
               fontsize=7, color='#000', fontweight='bold')

    ax.set_xlim(-10, sheet.width_mm + 10)
    ax.set_ylim(-10, sheet.height_mm + 10)
    ax.set_xlabel('mm', color='white')
    ax.set_ylabel('mm', color='white')
    ax.tick_params(colors='white')
    mat_info = f" | {sheet.material} {sheet.thickness}mm" if sheet.material else ""
    ax.set_title(f"Arkusz #{sheet.sheet_index + 1}{mat_info} | {sheet.used_width_mm:.0f} x {sheet.used_height_mm:.0f} mm | Util: {sheet.utilization_pct:.1f}%",
                color='white', fontsize=11)

    for spine in ax.spines.values():
        spine.set_color('#4a4a4a')

    plt.tight_layout()

    # Do base64
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=120, facecolor='#0f0f0f')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()

    if output_path:
        plt.savefig(output_path, dpi=150, facecolor='#0f0f0f')

    return img_base64


def visualize_part(part: PartData) -> str:
    """Wizualizacja pojedynczego detalu - zwraca base64 PNG"""
    fig, ax = plt.subplots(1, 1, figsize=(6, 6))
    ax.set_aspect('equal')
    ax.set_facecolor('#1a1a1a')
    fig.patch.set_facecolor('#0f0f0f')

    if part.outer_contour:
        poly = MplPolygon(part.outer_contour, closed=True, facecolor='#3b82f6',
                         edgecolor='#22c55e', linewidth=2, alpha=0.8)
        ax.add_patch(poly)

        for hole in part.holes:
            h_poly = MplPolygon(hole, closed=True, facecolor='#1a1a1a',
                               edgecolor='#ef4444', linewidth=1.5)
            ax.add_patch(h_poly)
    else:
        ax.add_patch(Rectangle(
            (0, 0), part.width_mm, part.height_mm,
            facecolor='#3b82f6', edgecolor='#22c55e', linewidth=2, alpha=0.8
        ))

    ax.set_xlim(-5, part.width_mm + 5)
    ax.set_ylim(-5, part.height_mm + 5)
    ax.tick_params(colors='white')
    ax.set_title(f"{part.name}\n{part.width_mm:.1f} x {part.height_mm:.1f} mm",
                color='white', fontsize=10)

    for spine in ax.spines.values():
        spine.set_color('#4a4a4a')

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, facecolor='#0f0f0f')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()

    return img_base64


def generate_html_report(results: List[ComparisonResult], output_path: Path):
    """Generuj kompletny raport HTML"""

    html = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <title>Raport Nesting - NewERP vs CypNest</title>
    <style>
        :root {{
            --bg-dark: #0f0f0f;
            --bg-card: #1a1a1a;
            --text-primary: #fff;
            --text-secondary: #a0a0a0;
            --accent: #8b5cf6;
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Segoe UI', sans-serif; background: var(--bg-dark); color: var(--text-primary); padding: 20px; }}
        .container {{ max-width: 1600px; margin: 0 auto; }}
        h1 {{ color: var(--accent); margin-bottom: 10px; }}
        h2 {{ color: var(--text-primary); margin: 30px 0 15px; border-bottom: 2px solid var(--accent); padding-bottom: 10px; }}
        h3 {{ color: var(--accent); margin: 20px 0 10px; }}

        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
        .summary-item {{ background: var(--bg-card); padding: 20px; border-radius: 8px; text-align: center; }}
        .summary-value {{ font-size: 1.8em; font-weight: bold; }}
        .summary-label {{ color: var(--text-secondary); margin-top: 5px; }}

        .status-ok {{ color: var(--success); }}
        .status-warn {{ color: var(--warning); }}
        .status-fail {{ color: var(--danger); }}

        .folder-section {{ background: var(--bg-card); border-radius: 12px; padding: 20px; margin: 20px 0; }}
        .folder-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
        .folder-name {{ font-size: 1.3em; font-weight: bold; }}
        .folder-status {{ padding: 5px 15px; border-radius: 20px; font-weight: bold; }}

        .comparison-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 15px 0; }}
        .comparison-box {{ background: #2d2d2d; padding: 15px; border-radius: 8px; }}
        .comparison-title {{ color: var(--text-secondary); margin-bottom: 10px; font-size: 0.9em; }}
        .comparison-value {{ font-size: 1.4em; font-weight: bold; }}
        .comparison-diff {{ font-size: 0.9em; margin-top: 5px; }}

        .sheets-container {{ display: flex; flex-wrap: wrap; gap: 20px; margin: 20px 0; }}
        .sheet-img {{ max-width: 100%; border-radius: 8px; border: 1px solid #333; }}

        .parts-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 15px; margin: 15px 0; }}
        .part-card {{ background: #2d2d2d; border-radius: 8px; padding: 15px; text-align: center; }}
        .part-img {{ max-width: 100%; border-radius: 6px; margin-bottom: 10px; }}
        .part-name {{ font-weight: bold; margin-bottom: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        .part-info {{ font-size: 0.85em; color: var(--text-secondary); }}

        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #333; }}
        th {{ background: #2d2d2d; color: var(--accent); }}
        tr:hover {{ background: #252525; }}
        .number {{ text-align: right; font-family: monospace; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Raport Porownawczy: NewERP vs CypNest</h1>
        <p style="color: var(--text-secondary);">Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

        <div class="summary">
            <div class="summary-item">
                <div class="summary-value">{len(results)}</div>
                <div class="summary-label">Folderow testowych</div>
            </div>
            <div class="summary-item">
                <div class="summary-value status-ok">{sum(1 for r in results if r.status == 'OK')}</div>
                <div class="summary-label">OK (≤2%)</div>
            </div>
            <div class="summary-item">
                <div class="summary-value status-warn">{sum(1 for r in results if r.status == 'WARN')}</div>
                <div class="summary-label">WARN (2-5%)</div>
            </div>
            <div class="summary-item">
                <div class="summary-value status-fail">{sum(1 for r in results if r.status == 'FAIL')}</div>
                <div class="summary-label">FAIL (>5%)</div>
            </div>
        </div>
"""

    for result in results:
        status_class = 'status-ok' if result.status == 'OK' else ('status-warn' if result.status == 'WARN' else 'status-fail')
        status_bg = '#22c55e33' if result.status == 'OK' else ('#f59e0b33' if result.status == 'WARN' else '#ef444433')

        html += f"""
        <div class="folder-section">
            <div class="folder-header">
                <span class="folder-name">{result.folder}</span>
                <span class="folder-status {status_class}" style="background: {status_bg};">{result.status}</span>
            </div>

            <div class="comparison-grid">
                <div class="comparison-box">
                    <div class="comparison-title">DLUGOSC CIECIA</div>
                    <div class="comparison-value">NewERP: {result.newerp_cut_length_m:.2f} m</div>
                    <div class="comparison-value" style="color: var(--text-secondary);">CypNest: {result.cypnest_cut_length_m:.2f} m</div>
                    <div class="comparison-diff {status_class}">Roznica: {result.cut_length_diff_pct:+.1f}%</div>
                </div>
                <div class="comparison-box">
                    <div class="comparison-title">CZAS CIECIA</div>
                    <div class="comparison-value">NewERP: {result.newerp_time_s:.0f}s ({result.newerp_time_s/60:.1f} min)</div>
                    <div class="comparison-value" style="color: var(--text-secondary);">CypNest: {result.cypnest_time_s:.0f}s ({result.cypnest_time_s/60:.1f} min)</div>
                    <div class="comparison-diff">Roznica: {result.time_diff_pct:+.1f}%</div>
                </div>
            </div>
"""

        # Wizualizacja arkuszy
        if result.sheets:
            html += """<h3>Wizualizacja Nestingu</h3><div class="sheets-container">"""
            for sheet in result.sheets:
                img_base64 = visualize_sheet(sheet)
                html += f"""
                <div>
                    <img src="data:image/png;base64,{img_base64}" class="sheet-img" alt="Arkusz {sheet.sheet_index + 1}">
                </div>
"""
            html += "</div>"

        # Tabela detali
        if result.parts:
            html += """
            <h3>Szczegoly Detali</h3>
            <table>
                <thead>
                    <tr>
                        <th>Detal</th>
                        <th>Material</th>
                        <th class="number">Qty</th>
                        <th class="number">Wymiary [mm]</th>
                        <th class="number">Ciecie [m]</th>
                        <th class="number">Przebicia</th>
                        <th class="number">Czas [s]</th>
                    </tr>
                </thead>
                <tbody>
"""
            for part in result.parts:
                html += f"""
                    <tr>
                        <td>{part.name[:40]}</td>
                        <td>{part.material} {part.thickness_mm}mm</td>
                        <td class="number">{part.qty}</td>
                        <td class="number">{part.width_mm:.1f} x {part.height_mm:.1f}</td>
                        <td class="number">{part.cut_length_mm/1000:.2f}</td>
                        <td class="number">{part.pierce_count}</td>
                        <td class="number">{part.total_time_s:.1f}</td>
                    </tr>
"""
            html += "</tbody></table>"

        # Wizualizacja detali
        if result.parts and len(result.parts) <= 10:
            html += """<h3>Wizualizacja Detali</h3><div class="parts-grid">"""
            for part in result.parts[:10]:
                img_base64 = visualize_part(part)
                html += f"""
                <div class="part-card">
                    <img src="data:image/png;base64,{img_base64}" class="part-img" alt="{part.name}">
                    <div class="part-name" title="{part.name}">{part.name[:20]}</div>
                    <div class="part-info">{part.width_mm:.0f} x {part.height_mm:.0f} mm | {part.cut_length_mm/1000:.2f}m</div>
                </div>
"""
            html += "</div>"

        html += "</div>"

    html += """
    </div>
</body>
</html>
"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Raport zapisany: {output_path}")


def process_folder(folder: Path, calculator: DynamicCalculator) -> ComparisonResult:
    """Przetwarzaj folder testowy"""
    result = ComparisonResult(folder=folder.name)

    # Znajdz WSZYSTKIE XLSX z CypNest i polacz dane
    xlsx_files = list(folder.glob('*.xlsx'))
    all_cypnest_parts = []
    total_cypnest_cut = 0
    total_cypnest_time = 0

    for xlsx in xlsx_files:
        data = parse_cypnest_xlsx(xlsx)
        if data and data.parts:
            all_cypnest_parts.extend(data.parts)
            total_cypnest_cut += data.total_cut_length_m
            total_cypnest_time += data.total_cut_time_s

    result.cypnest_cut_length_m = total_cypnest_cut
    result.cypnest_time_s = total_cypnest_time

    # Analizuj DXF
    dxf_files = list(folder.glob('*.dxf'))
    parts = []

    print(f"  DXF files: {len(dxf_files)}, CypNest parts: {len(all_cypnest_parts)}")

    for dxf_path in dxf_files:
        part = analyze_dxf(dxf_path, calculator)
        if part:
            # Dopasuj qty z CypNest
            matched = False
            for cp in all_cypnest_parts:
                if match_part_names(part.name, cp['name']):
                    print(f"    Match: {part.name[:30]} -> {cp['name'][:30]} qty={cp['qty']}")
                    part.qty = cp['qty']
                    matched = True
                    break

            if not matched and all_cypnest_parts:
                print(f"    NO MATCH: {part.name[:40]}")

            parts.append(part)

    result.parts = parts

    # Oblicz sumy
    # Cut length BEZ lead-in (CypNest tez nie wlicza lead-in do "Cut Length")
    total_cut_length = sum(p.cut_length_mm * p.qty for p in parts) / 1000
    total_lead_in = sum(p.lead_in_length_mm * p.qty for p in parts) / 1000
    total_time = sum(p.total_time_s * p.qty for p in parts)

    result.newerp_cut_length_m = total_cut_length  # BEZ lead-in
    result.newerp_time_s = total_time

    print(f"  (lead-in total: {total_lead_in:.2f}m - not included in cut length comparison)")

    # Szczegolowy rozklad czasow
    total_cut_time = sum(p.cut_time_s * p.qty for p in parts)
    total_lead_time = sum(p.lead_in_time_s * p.qty for p in parts)
    total_pierce_time = sum(p.pierce_time_s * p.qty for p in parts)
    total_rapid_time = sum(p.rapid_time_s * p.qty for p in parts)  # Rapid INSIDE parts (between contours)

    print(f"  === ROZKLAD CZASU ===")
    print(f"    Czas ciecia:        {total_cut_time:8.1f}s ({total_cut_time/60:.1f} min)")
    print(f"    Czas wpalen:        {total_lead_time:8.1f}s ({total_lead_time/60:.1f} min)")
    print(f"    Czas przebic:       {total_pierce_time:8.1f}s ({total_pierce_time/60:.1f} min)")
    print(f"    Rapid (w detalu):   {total_rapid_time:8.1f}s ({total_rapid_time/60:.1f} min) <- miedzy konturami wewnatrz detalu")
    print(f"    SUMA (bez sheets):  {total_time:8.1f}s ({total_time/60:.1f} min)")
    print(f"    CypNest:            {total_cypnest_time:8.1f}s ({total_cypnest_time/60:.1f} min)")

    # Porownanie
    if result.cypnest_cut_length_m > 0:
        result.cut_length_diff_pct = ((result.newerp_cut_length_m - result.cypnest_cut_length_m)
                                      / result.cypnest_cut_length_m * 100)
    if result.cypnest_time_s > 0:
        result.time_diff_pct = ((result.newerp_time_s - result.cypnest_time_s)
                                / result.cypnest_time_s * 100)

    # Status
    diff = abs(result.cut_length_diff_pct)
    if diff <= 2:
        result.status = 'OK'
    elif diff <= 5:
        result.status = 'WARN'
    else:
        result.status = 'FAIL'

    # NESTING - ODDZIELNY DLA KAZDEGO MATERIALU I GRUBOSCI
    if parts:
        # Grupuj detale wg materialu i grubosci
        groups = {}
        for part in parts:
            key = (part.material, part.thickness_mm)
            if key not in groups:
                groups[key] = []
            groups[key].append(part)

        print(f"  === GRUPY NESTINGU ===")
        for (mat, thick), group_parts in groups.items():
            total_qty = sum(p.qty for p in group_parts)
            print(f"    {mat} {thick}mm: {len(group_parts)} typow, {total_qty} szt")

        # Nesting dla kazdej grupy osobno
        sheet_w, sheet_h = 3000, 1500
        all_sheets = []
        for (mat, thick), group_parts in groups.items():
            group_sheets = simple_nesting(group_parts, sheet_w, sheet_h)
            # Oznacz arkusze materialem
            for sheet in group_sheets:
                sheet.material = mat
                sheet.thickness = thick
            all_sheets.extend(group_sheets)

        result.sheets = all_sheets

        # Oblicz rapid MIEDZY CZESCIAMI na kazdym arkuszu
        total_sheet_rapid_time = 0
        for sheet in all_sheets:
            sheet_rapid = calc_sheet_rapid_time(sheet, calculator)
            sheet.total_rapid_time_s = sheet_rapid
            total_sheet_rapid_time += sheet_rapid

        # Dodaj rapid miedzy czesciami do calkowitego czasu
        result.newerp_time_s += total_sheet_rapid_time

        print(f"  === RAPID MIEDZY CZESCIAMI ===")
        print(f"    Arkuszy:       {len(all_sheets)}")
        print(f"    Rapid sheets:  {total_sheet_rapid_time:8.1f}s ({total_sheet_rapid_time/60:.1f} min)")
        print(f"    NOWY TOTAL:    {result.newerp_time_s:8.1f}s ({result.newerp_time_s/60:.1f} min)")

    return result


def match_part_names(name1: str, name2: str) -> bool:
    """Dopasuj nazwy detali (rozne konwencje)"""
    import re

    def normalize(name):
        # Usun rozszerzenia
        name = name.lower().replace('.dxf', '')
        # Usun sufiksy z iloscia (np. "_1szt", "- 10szt", "_9szt")
        name = re.sub(r'[\s_-]*\d+\s*szt\.?$', '', name, flags=re.IGNORECASE)
        # Usun material i grubosc z konca (np. "_2mm_INOX", "-1.5mm-S235JR")
        name = re.sub(r'[\s_-]*\d+[.,]?\d*\s*mm[\s_-]*(inox|fe|s235|1\.4301|st42|s235jr)?[\s_-]*(laser)?t?', '', name, flags=re.IGNORECASE)
        # Normalizuj separatory ale zachowaj numery wersji
        name = re.sub(r'[\s_-]+', '_', name)
        return name.strip('_')

    def extract_part_number(name):
        """Wyodrebnij numer czesci (np. A035978-01 -> ('A035978', '01'))"""
        # Szukaj wzorca: nazwa-XX gdzie XX to 1-2 cyfrowa wersja (nie kod produktu)
        # A035978-01 -> ('A035978', '01')
        # 11-063143 -> ('11-063143', None) - to jest pelny kod, nie wersja
        match = re.search(r'([A-Za-z]+\d+)[\s_-](0?\d{1,2})(?:[\s_-]|$)', name)
        if match:
            # Upewnij sie ze suffix to wersja (1-2 cyfry), nie czesc kodu
            suffix = match.group(2)
            if len(suffix) <= 2:
                return match.group(1), suffix
        return name, None

    n1 = normalize(name1)
    n2 = normalize(name2)

    # Dokladne dopasowanie po normalizacji
    if n1 == n2:
        return True

    # Wyodrebnij numery czesci
    base1, num1 = extract_part_number(name1.lower())
    base2, num2 = extract_part_number(name2.lower())

    # Jesli oba maja numery wersji, musza sie zgadzac
    if num1 and num2:
        if num1 != num2:
            return False
        # Sprawdz czy bazy sa podobne
        b1 = re.sub(r'[\s_-]+', '', base1)
        b2 = re.sub(r'[\s_-]+', '', base2)
        if b1 == b2 or b1 in b2 or b2 in b1:
            return True

    # Jeden zawiera drugi (ale nie zbyt krotki)
    if len(n1) > 6 and len(n2) > 6:
        if n1 in n2 or n2 in n1:
            return True

    # Prefiks (pierwsze 10+ znakow)
    if len(n1) >= 10 and len(n2) >= 10 and n1[:10] == n2[:10]:
        return True

    return False


def main():
    parser = argparse.ArgumentParser(description="Porownanie NewERP vs CypNest z nestingiem")
    parser.add_argument("--folders", type=str, nargs='+', help="Foldery testowe")
    parser.add_argument("--base", type=str, default="C:/temp", help="Bazowy folder")
    parser.add_argument("--output", type=str, default="C:/temp/nesting_comparison_report.html")
    args = parser.parse_args()

    print("=" * 70)
    print("  NESTING COMPARISON: NewERP vs CypNest")
    print("=" * 70)

    calculator = DynamicCalculator()

    # Znajdz foldery testowe
    base = Path(args.base)
    if args.folders:
        folders = [base / f for f in args.folders]
    else:
        folders = [p for p in base.iterdir() if p.is_dir() and
                   (p.name.lower().startswith('test') and any(p.glob('*.dxf')))]

    print(f"\nZnaleziono {len(folders)} folderow testowych")

    results = []
    for folder in sorted(folders):
        print(f"\n{'='*50}")
        print(f"  {folder.name}")
        print(f"{'='*50}")

        result = process_folder(folder, calculator)
        results.append(result)

        print(f"  NewERP:  {result.newerp_cut_length_m:.2f} m | {result.newerp_time_s:.0f}s")
        print(f"  CypNest: {result.cypnest_cut_length_m:.2f} m | {result.cypnest_time_s:.0f}s")
        print(f"  Diff:    {result.cut_length_diff_pct:+.1f}% | Status: {result.status}")

    # Generuj raport
    output_path = Path(args.output)
    generate_html_report(results, output_path)

    # Podsumowanie
    print("\n" + "=" * 70)
    print("  PODSUMOWANIE")
    print("=" * 70)
    ok = sum(1 for r in results if r.status == 'OK')
    warn = sum(1 for r in results if r.status == 'WARN')
    fail = sum(1 for r in results if r.status == 'FAIL')
    print(f"  OK:   {ok}/{len(results)}")
    print(f"  WARN: {warn}/{len(results)}")
    print(f"  FAIL: {fail}/{len(results)}")
    print(f"\nRaport: {output_path}")


if __name__ == "__main__":
    main()
