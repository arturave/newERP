"""
Cost Diagnostic Report - Raport diagnostyczny kosztów
======================================================
Generuje szczegółowy raport HTML pokazujący każdy etap obliczeń kosztów.

Użycie:
    python scripts/cost_diagnostic_report.py --dxf-folder C:\temp\test2 --output report.html
"""

import os
import sys
import json
import math
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

# Dodaj ścieżkę projektu
sys.path.insert(0, str(Path(__file__).parent.parent))

from quotations.utils.dxf_loader import load_dxf, DXFPart
from quotations.utils.name_parser import parse_filename_with_folder_context

# Stałe
DENSITY_STEEL = 7850  # kg/m³
DENSITY_INOX = 8000   # kg/m³
DENSITY_ALU = 2700    # kg/m³


@dataclass
class PartAnalysis:
    """Analiza pojedynczego detalu"""
    name: str
    filepath: str

    # Wymiary
    width_mm: float = 0
    height_mm: float = 0
    thickness_mm: float = 0

    # Powierzchnie
    area_bbox_mm2: float = 0          # Prostokąt otaczający
    area_contour_mm2: float = 0       # Kontur zewnętrzny (bez otworów)
    area_net_mm2: float = 0           # Netto (kontur - otwory)

    # Obwód / cięcie
    perimeter_outer_mm: float = 0     # Obwód zewnętrzny
    perimeter_holes_mm: float = 0     # Obwód otworów
    perimeter_total_mm: float = 0     # Suma

    # Ilość
    quantity: int = 1

    # Materiał
    material: str = ""
    density_kg_m3: float = 8000

    # Wagi
    weight_bbox_kg: float = 0         # Waga z bbox
    weight_contour_kg: float = 0      # Waga z konturu
    weight_net_kg: float = 0          # Waga netto

    # Liczba przebić
    pierce_count: int = 0

    # Koszty jednostkowe (wszystkie modele)
    cost_material_bbox: float = 0
    cost_material_contour: float = 0
    cost_material_equal: float = 0
    cost_cutting: float = 0
    cost_piercing: float = 0
    cost_foil: float = 0


@dataclass
class SheetAnalysis:
    """Analiza arkusza"""
    sheet_id: int
    material: str
    thickness_mm: float

    # Wymiary
    width_mm: float = 0
    length_mm: float = 0
    length_used_mm: float = 0         # Przycięta długość (maxY z nestingu)

    # Powierzchnie
    area_nominal_mm2: float = 0       # Pełny arkusz
    area_used_mm2: float = 0          # Przycięty
    area_parts_mm2: float = 0         # Suma detali

    # Utilization
    utilization_pct: float = 0

    # Waga
    weight_nominal_kg: float = 0
    weight_used_kg: float = 0

    # Koszt
    cost_nominal_pln: float = 0
    cost_used_pln: float = 0

    # Cięcie
    cut_length_m: float = 0
    cut_time_classic_s: float = 0
    cut_time_dynamic_s: float = 0

    # Detale
    parts: List[str] = field(default_factory=list)


@dataclass
class DiagnosticReport:
    """Pełny raport diagnostyczny"""
    timestamp: str
    dxf_folder: str

    # Globalne
    total_parts: int = 0
    total_sheets: int = 0

    # Sumy
    total_cut_length_m: float = 0
    total_cut_time_s: float = 0
    total_material_cost_pln: float = 0
    total_cutting_cost_pln: float = 0

    # Detale
    parts: List[PartAnalysis] = field(default_factory=list)
    sheets: List[SheetAnalysis] = field(default_factory=list)

    # Porównanie modeli
    comparison: Dict = field(default_factory=dict)


def calculate_perimeter(contour: List[Tuple[float, float]]) -> float:
    """Oblicz obwód konturu"""
    if len(contour) < 2:
        return 0

    perimeter = 0
    for i in range(len(contour) - 1):
        dx = contour[i+1][0] - contour[i][0]
        dy = contour[i+1][1] - contour[i][1]
        perimeter += math.sqrt(dx*dx + dy*dy)

    # Zamknij kontur jeśli nie zamknięty
    if contour[0] != contour[-1]:
        dx = contour[0][0] - contour[-1][0]
        dy = contour[0][1] - contour[-1][1]
        perimeter += math.sqrt(dx*dx + dy*dy)

    return perimeter


def get_density(material: str) -> float:
    """Pobierz gęstość materiału"""
    material_upper = material.upper()
    if '1.4' in material_upper or 'INOX' in material_upper or 'STAINLESS' in material_upper:
        return DENSITY_INOX
    elif 'ALU' in material_upper:
        return DENSITY_ALU
    else:
        return DENSITY_STEEL


def analyze_dxf_file(filepath: str) -> Optional[PartAnalysis]:
    """Przeanalizuj pojedynczy plik DXF - pełna analiza wszystkich encji do cięcia"""
    import ezdxf

    part = load_dxf(filepath)
    if not part:
        return None

    # Parsuj nazwę pliku
    filename = os.path.basename(filepath)
    try:
        from pathlib import Path as PathLib
        parsed = parse_filename_with_folder_context(PathLib(filepath), os.path.dirname(filepath))
    except Exception:
        parsed = {}

    analysis = PartAnalysis(
        name=part.name,
        filepath=filepath,
        width_mm=part.width,
        height_mm=part.height,
        thickness_mm=parsed.get('thickness', 0) or 2.0,
        material=parsed.get('material', '') or '1.4301',
        quantity=parsed.get('quantity', 1) or 1
    )

    # Powierzchnie
    analysis.area_bbox_mm2 = part.width * part.height
    analysis.area_contour_mm2 = part.contour_area

    # Oblicz powierzchnię netto (kontur - otwory)
    holes_area = 0
    for hole in part.holes:
        if len(hole) >= 3:
            n = len(hole)
            area = 0
            for i in range(n):
                j = (i + 1) % n
                area += hole[i][0] * hole[j][1]
                area -= hole[j][0] * hole[i][1]
            holes_area += abs(area) / 2.0

    analysis.area_net_mm2 = analysis.area_contour_mm2 - holes_area

    # === PEŁNA ANALIZA DŁUGOŚCI CIĘCIA Z DXF ===
    # (nie tylko kontur zewnętrzny, ale WSZYSTKIE encje do cięcia)
    try:
        doc = ezdxf.readfile(filepath)
        msp = doc.modelspace()

        # Warstwy do ignorowania
        IGNORE_LAYERS = {'AM_', 'RAMKA', 'WYMIARY', 'DIM', 'TEXT', 'DEFPOINTS'}

        total_cut_length = 0
        pierce_count = 0

        for entity in msp:
            layer = entity.dxf.layer.upper()

            # Ignoruj warstwy pomocnicze
            if any(ign in layer for ign in IGNORE_LAYERS):
                continue

            etype = entity.dxftype()

            if etype == 'CIRCLE':
                r = entity.dxf.radius
                perimeter = 2 * math.pi * r
                total_cut_length += perimeter
                pierce_count += 1

            elif etype == 'ARC':
                r = entity.dxf.radius
                sa, ea = entity.dxf.start_angle, entity.dxf.end_angle
                if ea < sa:
                    ea += 360
                arc_length = math.radians(ea - sa) * r
                total_cut_length += arc_length
                # Łuki zwykle nie wymagają osobnego przebicia (są częścią konturu)

            elif etype == 'LINE':
                start = entity.dxf.start
                end = entity.dxf.end
                length = math.sqrt((end.x - start.x)**2 + (end.y - start.y)**2)
                total_cut_length += length

            elif etype == 'LWPOLYLINE':
                pts = list(entity.get_points('xy'))
                for i in range(len(pts) - 1):
                    dx = pts[i+1][0] - pts[i][0]
                    dy = pts[i+1][1] - pts[i][1]
                    total_cut_length += math.sqrt(dx*dx + dy*dy)
                if entity.closed and pts:
                    dx = pts[0][0] - pts[-1][0]
                    dy = pts[0][1] - pts[-1][1]
                    total_cut_length += math.sqrt(dx*dx + dy*dy)
                pierce_count += 1

        analysis.perimeter_total_mm = total_cut_length
        analysis.pierce_count = max(pierce_count, 1)

        # Rozdziel na zewnętrzny i otwory (uproszczenie - bierzemy z load_dxf)
        analysis.perimeter_outer_mm = calculate_perimeter(part.outer_contour)
        analysis.perimeter_holes_mm = total_cut_length - analysis.perimeter_outer_mm

    except Exception as e:
        # Fallback do starej metody
        analysis.perimeter_outer_mm = calculate_perimeter(part.outer_contour)
        for hole in part.holes:
            analysis.perimeter_holes_mm += calculate_perimeter(hole)
        analysis.perimeter_total_mm = analysis.perimeter_outer_mm + analysis.perimeter_holes_mm
        analysis.pierce_count = 1 + len(part.holes)

    # Gęstość
    analysis.density_kg_m3 = get_density(analysis.material)

    # Wagi (mm² * mm * kg/m³ / 10^9 = kg)
    thickness_m = analysis.thickness_mm / 1000
    analysis.weight_bbox_kg = (analysis.area_bbox_mm2 / 1_000_000) * thickness_m * analysis.density_kg_m3
    analysis.weight_contour_kg = (analysis.area_contour_mm2 / 1_000_000) * thickness_m * analysis.density_kg_m3
    analysis.weight_net_kg = (analysis.area_net_mm2 / 1_000_000) * thickness_m * analysis.density_kg_m3

    return analysis


def load_pricing_data() -> Dict:
    """Wczytaj dane cenowe - używamy domyślnych stawek dla testów"""
    # Domyślne stawki testowe (dla INOX 2mm)
    print("  Uzywam domyslnych stawek testowych")
    return {
        'materials': {
            '1.4301_2.0': {'material': '1.4301', 'thickness': 2.0, 'price_per_kg': 25.0}
        },
        'cutting': {
            '1.4301_2.0': {'material': '1.4301', 'thickness': 2.0, 'price_per_m': 3.5}
        },
        'piercing': {
            '1.4301_2.0': {'material': '1.4301', 'thickness': 2.0, 'price_per_pierce': 0.30}
        },
        'foil': {
            '1.4301_2.0': {'material': '1.4301', 'thickness': 2.0, 'price_per_m': 0.50}
        }
    }


def get_material_price_per_kg(material: str, thickness: float, pricing: Dict) -> float:
    """Pobierz cenę materiału za kg"""
    # Szukaj w cache
    for key, data in pricing.get('materials', {}).items():
        if material.upper() in key.upper():
            if abs(data.get('thickness', 0) - thickness) < 0.1:
                return data.get('price_per_kg', 0)

    # Domyślne ceny
    if '1.4' in material.upper() or 'INOX' in material.upper():
        return 25.0  # PLN/kg dla INOX
    elif 'ALU' in material.upper():
        return 15.0
    else:
        return 5.0  # Stal


def get_cutting_rate(material: str, thickness: float, pricing: Dict) -> float:
    """Pobierz stawkę cięcia za metr"""
    for key, data in pricing.get('cutting', {}).items():
        if material.upper() in key.upper():
            if abs(data.get('thickness', 0) - thickness) < 0.1:
                return data.get('price_per_m', 0)

    # Domyślne stawki
    if '1.4' in material.upper() or 'INOX' in material.upper():
        return 3.5  # PLN/m dla INOX
    elif 'ALU' in material.upper():
        return 2.5
    else:
        return 2.0


def get_pierce_rate(material: str, thickness: float, pricing: Dict) -> float:
    """Pobierz stawkę za przebicie"""
    for key, data in pricing.get('piercing', {}).items():
        if material.upper() in key.upper():
            if abs(data.get('thickness', 0) - thickness) < 0.1:
                return data.get('price_per_pierce', 0)

    # Domyślne
    return 0.30  # PLN/przebicie


def calculate_costs(parts: List[PartAnalysis], pricing: Dict) -> None:
    """Oblicz koszty dla wszystkich modeli alokacji"""
    if not parts:
        return

    # Sumy powierzchni (dla alokacji proporcjonalnej)
    total_bbox = sum(p.area_bbox_mm2 * p.quantity for p in parts)
    total_contour = sum(p.area_contour_mm2 * p.quantity for p in parts)
    total_qty = sum(p.quantity for p in parts)

    # Oblicz łączny koszt arkusza (uproszczenie - suma wag * cena)
    total_weight = sum(p.weight_contour_kg * p.quantity for p in parts)

    # Pobierz cenę materiału (zakładam ten sam materiał dla wszystkich)
    material = parts[0].material
    thickness = parts[0].thickness_mm
    price_per_kg = get_material_price_per_kg(material, thickness, pricing)
    cutting_rate = get_cutting_rate(material, thickness, pricing)
    pierce_rate = get_pierce_rate(material, thickness, pricing)

    total_material_cost = total_weight * price_per_kg

    for part in parts:
        # Model BBOX (proporcjonalnie do bbox)
        if total_bbox > 0:
            share_bbox = (part.area_bbox_mm2 * part.quantity) / total_bbox
            part.cost_material_bbox = total_material_cost * share_bbox / part.quantity

        # Model CONTOUR (proporcjonalnie do konturu)
        if total_contour > 0:
            share_contour = (part.area_contour_mm2 * part.quantity) / total_contour
            part.cost_material_contour = total_material_cost * share_contour / part.quantity

        # Model EQUAL (równy podział)
        if total_qty > 0:
            part.cost_material_equal = total_material_cost / total_qty

        # Koszt cięcia (per detal)
        cut_length_m = part.perimeter_total_mm / 1000
        part.cost_cutting = cut_length_m * cutting_rate

        # Koszt przebić
        part.cost_piercing = part.pierce_count * pierce_rate

        # Koszt folii (tylko INOX <= 5mm)
        if '1.4' in part.material.upper() and part.thickness_mm <= 5:
            foil_rate = 0.50  # PLN/m
            part.cost_foil = cut_length_m * foil_rate


def generate_html_report(report: DiagnosticReport) -> str:
    """Generuj raport HTML"""
    html = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Raport Diagnostyczny Kosztów - {report.timestamp}</title>
    <style>
        :root {{
            --bg-dark: #0f0f0f;
            --bg-card: #1a1a1a;
            --bg-input: #2d2d2d;
            --text-primary: #ffffff;
            --text-secondary: #a0a0a0;
            --accent-primary: #8b5cf6;
            --accent-success: #22c55e;
            --accent-warning: #f59e0b;
            --accent-danger: #ef4444;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: var(--bg-dark);
            color: var(--text-primary);
            padding: 20px;
            line-height: 1.6;
        }}

        .container {{ max-width: 1400px; margin: 0 auto; }}

        h1 {{
            color: var(--accent-primary);
            margin-bottom: 10px;
            font-size: 2em;
        }}

        h2 {{
            color: var(--text-primary);
            margin: 30px 0 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid var(--accent-primary);
        }}

        h3 {{
            color: var(--accent-primary);
            margin: 20px 0 10px;
        }}

        .meta {{
            color: var(--text-secondary);
            margin-bottom: 30px;
        }}

        .card {{
            background: var(--bg-card);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid #333;
        }}

        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #333;
        }}

        .card-title {{
            font-size: 1.2em;
            font-weight: bold;
            color: var(--accent-primary);
        }}

        .badge {{
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: bold;
        }}

        .badge-primary {{ background: var(--accent-primary); }}
        .badge-success {{ background: var(--accent-success); }}
        .badge-warning {{ background: var(--accent-warning); color: #000; }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}

        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #333;
        }}

        th {{
            background: var(--bg-input);
            color: var(--accent-primary);
            font-weight: bold;
        }}

        tr:hover {{ background: var(--bg-input); }}

        .number {{ text-align: right; font-family: monospace; }}

        .highlight {{
            background: linear-gradient(135deg, var(--accent-primary)22, transparent);
            border-left: 4px solid var(--accent-primary);
        }}

        .comparison-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin: 20px 0;
        }}

        .comparison-item {{
            background: var(--bg-input);
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }}

        .comparison-label {{
            color: var(--text-secondary);
            font-size: 0.9em;
            margin-bottom: 5px;
        }}

        .comparison-value {{
            font-size: 1.5em;
            font-weight: bold;
            color: var(--accent-primary);
        }}

        .visualization {{
            background: var(--bg-input);
            padding: 20px;
            border-radius: 8px;
            margin: 15px 0;
            font-family: monospace;
            white-space: pre;
            overflow-x: auto;
        }}

        .formula {{
            background: #1e1e3f;
            padding: 10px 15px;
            border-radius: 6px;
            font-family: monospace;
            margin: 10px 0;
            border-left: 3px solid var(--accent-warning);
        }}

        .diff-positive {{ color: var(--accent-success); }}
        .diff-negative {{ color: var(--accent-danger); }}

        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin: 20px 0;
        }}

        .summary-item {{
            background: var(--bg-card);
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            border: 1px solid #333;
        }}

        .summary-value {{
            font-size: 2em;
            font-weight: bold;
            color: var(--accent-primary);
        }}

        .summary-label {{
            color: var(--text-secondary);
            margin-top: 5px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Raport Diagnostyczny Kosztów</h1>
        <div class="meta">
            <p>Data: {report.timestamp}</p>
            <p>Folder DXF: {report.dxf_folder}</p>
        </div>

        <div class="summary-grid">
            <div class="summary-item">
                <div class="summary-value">{report.total_parts}</div>
                <div class="summary-label">Detali</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{report.total_cut_length_m:.2f} m</div>
                <div class="summary-label">Długość cięcia</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{report.total_material_cost_pln:.2f} PLN</div>
                <div class="summary-label">Koszt materiału</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{report.total_cutting_cost_pln:.2f} PLN</div>
                <div class="summary-label">Koszt cięcia</div>
            </div>
        </div>

        <h2>Porównanie Modeli Alokacji</h2>
        <div class="card">
            <table>
                <thead>
                    <tr>
                        <th>Detal</th>
                        <th>Qty</th>
                        <th class="number">BBOX [PLN]</th>
                        <th class="number">CONTOUR [PLN]</th>
                        <th class="number">EQUAL [PLN]</th>
                        <th class="number">Różnica BBOX vs CONTOUR</th>
                    </tr>
                </thead>
                <tbody>
"""

    for part in report.parts:
        diff = part.cost_material_bbox - part.cost_material_contour
        diff_pct = (diff / part.cost_material_contour * 100) if part.cost_material_contour > 0 else 0
        diff_class = "diff-positive" if diff > 0 else "diff-negative"

        html += f"""
                    <tr>
                        <td>{part.name}</td>
                        <td class="number">{part.quantity}</td>
                        <td class="number">{part.cost_material_bbox:.2f}</td>
                        <td class="number">{part.cost_material_contour:.2f}</td>
                        <td class="number">{part.cost_material_equal:.2f}</td>
                        <td class="number {diff_class}">{diff:+.2f} ({diff_pct:+.1f}%)</td>
                    </tr>
"""

    html += """
                </tbody>
            </table>
        </div>

        <h2>Szczegóły Detali</h2>
"""

    for part in report.parts:
        # Wizualizacja ASCII powierzchni
        bbox_ratio = part.area_contour_mm2 / part.area_bbox_mm2 if part.area_bbox_mm2 > 0 else 0
        contour_width = int(bbox_ratio * 40)

        viz = f"""
┌{'─' * 42}┐
│  BBOX: {part.area_bbox_mm2:,.0f} mm²{' ' * (42 - 20 - len(f'{part.area_bbox_mm2:,.0f}'))}│
│  ┌{'─' * contour_width}┐{' ' * (40 - contour_width)}│
│  │ CONTOUR: {part.area_contour_mm2:,.0f} mm²{' ' * (contour_width - 15 - len(f'{part.area_contour_mm2:,.0f}'))}│{' ' * (40 - contour_width)}│
│  │ ({bbox_ratio*100:.1f}% of bbox){' ' * (contour_width - 17 - len(f'{bbox_ratio*100:.1f}'))}│{' ' * (40 - contour_width)}│
│  └{'─' * contour_width}┘{' ' * (40 - contour_width)}│
└{'─' * 42}┘"""

        html += f"""
        <div class="card">
            <div class="card-header">
                <span class="card-title">{part.name}</span>
                <span class="badge badge-primary">{part.material} / {part.thickness_mm}mm</span>
            </div>

            <h3>Wymiary</h3>
            <table>
                <tr><td>Bounding Box</td><td class="number">{part.width_mm:.2f} × {part.height_mm:.2f} mm</td></tr>
                <tr><td>Grubość</td><td class="number">{part.thickness_mm:.2f} mm</td></tr>
                <tr><td>Ilość</td><td class="number">{part.quantity} szt</td></tr>
            </table>

            <h3>Powierzchnie</h3>
            <div class="visualization">{viz}</div>
            <table>
                <tr><td>Bbox (prostokąt otaczający)</td><td class="number">{part.area_bbox_mm2:,.2f} mm²</td></tr>
                <tr><td>Contour (kontur zewnętrzny)</td><td class="number">{part.area_contour_mm2:,.2f} mm²</td></tr>
                <tr><td>Net (po odjęciu otworów)</td><td class="number">{part.area_net_mm2:,.2f} mm²</td></tr>
                <tr class="highlight"><td>Różnica Bbox vs Contour</td><td class="number">{part.area_bbox_mm2 - part.area_contour_mm2:,.2f} mm² ({(1 - bbox_ratio) * 100:.1f}%)</td></tr>
            </table>

            <h3>Wagi (gęstość: {part.density_kg_m3} kg/m³)</h3>
            <div class="formula">Waga = Powierzchnia [m²] × Grubość [m] × Gęstość [kg/m³]</div>
            <table>
                <tr><td>Waga (z bbox)</td><td class="number">{part.weight_bbox_kg:.4f} kg</td></tr>
                <tr><td>Waga (z konturu)</td><td class="number">{part.weight_contour_kg:.4f} kg</td></tr>
                <tr><td>Waga (netto)</td><td class="number">{part.weight_net_kg:.4f} kg</td></tr>
            </table>

            <h3>Cięcie</h3>
            <table>
                <tr><td>Obwód zewnętrzny</td><td class="number">{part.perimeter_outer_mm:,.2f} mm ({part.perimeter_outer_mm/1000:.2f} m)</td></tr>
                <tr><td>Obwód otworów</td><td class="number">{part.perimeter_holes_mm:,.2f} mm ({part.perimeter_holes_mm/1000:.2f} m)</td></tr>
                <tr class="highlight"><td>Suma (cut length)</td><td class="number">{part.perimeter_total_mm:,.2f} mm ({part.perimeter_total_mm/1000:.2f} m)</td></tr>
                <tr><td>Liczba przebić</td><td class="number">{part.pierce_count} szt</td></tr>
            </table>

            <h3>Alokacja Materiału (koszt jednostkowy)</h3>
            <div class="comparison-grid">
                <div class="comparison-item">
                    <div class="comparison-label">Model BBOX</div>
                    <div class="comparison-value">{part.cost_material_bbox:.2f} PLN</div>
                </div>
                <div class="comparison-item">
                    <div class="comparison-label">Model CONTOUR</div>
                    <div class="comparison-value">{part.cost_material_contour:.2f} PLN</div>
                </div>
                <div class="comparison-item">
                    <div class="comparison-label">Model EQUAL</div>
                    <div class="comparison-value">{part.cost_material_equal:.2f} PLN</div>
                </div>
            </div>

            <h3>Inne Koszty (jednostkowe)</h3>
            <table>
                <tr><td>Koszt cięcia</td><td class="number">{part.cost_cutting:.2f} PLN</td></tr>
                <tr><td>Koszt przebić</td><td class="number">{part.cost_piercing:.2f} PLN</td></tr>
                <tr><td>Koszt folii</td><td class="number">{part.cost_foil:.2f} PLN</td></tr>
            </table>
        </div>
"""

    html += """
    </div>
</body>
</html>
"""
    return html


def main():
    parser = argparse.ArgumentParser(description='Generuj raport diagnostyczny kosztów')
    parser.add_argument('--dxf-folder', type=str, default=r'C:\temp\test2',
                       help='Folder z plikami DXF')
    parser.add_argument('--output', type=str, default='cost_diagnostic_report.html',
                       help='Nazwa pliku wyjściowego HTML')
    args = parser.parse_args()

    print(f"=== Raport Diagnostyczny Kosztów ===")
    print(f"Folder DXF: {args.dxf_folder}")
    print()

    # Wczytaj dane cenowe
    print("Ładowanie danych cenowych z Supabase...")
    pricing = load_pricing_data()

    # Znajdź pliki DXF
    dxf_folder = Path(args.dxf_folder)
    dxf_files = list(dxf_folder.glob("*.dxf"))
    print(f"Znaleziono {len(dxf_files)} plików DXF")

    # Przeanalizuj każdy plik
    parts = []
    for dxf_file in dxf_files:
        print(f"  Analizuję: {dxf_file.name}...")
        analysis = analyze_dxf_file(str(dxf_file))
        if analysis:
            parts.append(analysis)
            print(f"    OK: {analysis.width_mm:.2f} x {analysis.height_mm:.2f} mm, "
                  f"contour: {analysis.area_contour_mm2:,.0f} mm2, "
                  f"cut: {analysis.perimeter_total_mm/1000:.2f} m")
        else:
            print(f"    BŁĄD: Nie udało się wczytać")

    print()

    # Oblicz koszty
    print("Obliczanie kosztów...")
    calculate_costs(parts, pricing)

    # Utwórz raport
    report = DiagnosticReport(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        dxf_folder=str(args.dxf_folder),
        total_parts=sum(p.quantity for p in parts),
        parts=parts
    )

    # Oblicz sumy
    report.total_cut_length_m = sum(p.perimeter_total_mm / 1000 * p.quantity for p in parts)
    report.total_material_cost_pln = sum(p.cost_material_contour * p.quantity for p in parts)
    report.total_cutting_cost_pln = sum(p.cost_cutting * p.quantity for p in parts)

    # Generuj HTML
    print(f"Generowanie raportu HTML...")
    html = generate_html_report(report)

    # Zapisz
    output_path = Path(args.dxf_folder) / args.output
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\nRaport zapisany: {output_path}")
    print()
    print("=== PODSUMOWANIE ===")
    print(f"Detali: {report.total_parts}")
    print(f"Długość cięcia: {report.total_cut_length_m:.2f} m")
    print(f"Koszt materiału (CONTOUR): {report.total_material_cost_pln:.2f} PLN")
    print(f"Koszt cięcia: {report.total_cutting_cost_pln:.2f} PLN")

    # Porównanie z CypNest
    print()
    print("=== PORÓWNANIE Z CYPNEST ===")
    cypnest_cut_length = 18.81
    diff_cut = report.total_cut_length_m - cypnest_cut_length
    diff_pct = (diff_cut / cypnest_cut_length) * 100
    print(f"CypNest cut length: {cypnest_cut_length:.2f} m")
    print(f"NewERP cut length:  {report.total_cut_length_m:.2f} m")
    print(f"Różnica: {diff_cut:+.2f} m ({diff_pct:+.1f}%)")


if __name__ == "__main__":
    main()
