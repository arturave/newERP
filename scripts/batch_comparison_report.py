#!/usr/bin/env python3
"""
Skrypt do zbiorczej analizy i porownania wynikow NewERP vs CypNest
dla wielu folderow testowych.
"""

import argparse
import json
import sys
import math
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Dodaj sciezke do glownego katalogu projektu
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pandas as pd
    import ezdxf
except ImportError as e:
    print(f"Brak wymaganej biblioteki: {e}")
    print("Zainstaluj: pip install pandas openpyxl ezdxf")
    sys.exit(1)


@dataclass
class PartData:
    """Dane pojedynczego detalu"""
    name: str
    qty: int
    width_mm: float
    height_mm: float
    cut_length_m: float
    contour_area_mm2: float = 0
    bbox_area_mm2: float = 0
    thickness_mm: float = 0
    material: str = ""


@dataclass
class SheetData:
    """Dane arkusza z nestingu"""
    name: str
    plate_width_mm: float
    plate_height_mm: float
    utilization_pct: float
    cut_length_m: float
    cut_time_s: int
    parts_count: int


@dataclass
class CypNestData:
    """Dane referencyjne z CypNest"""
    source_file: str
    material: str
    thickness_mm: float
    total_cut_length_m: float
    total_cut_time_s: int
    total_parts: int
    sheets: List[SheetData] = field(default_factory=list)
    parts: List[PartData] = field(default_factory=list)


@dataclass
class NewERPData:
    """Dane obliczone przez NewERP"""
    total_cut_length_m: float
    total_parts: int
    parts: List[PartData] = field(default_factory=list)


@dataclass
class ComparisonResult:
    """Wynik porownania"""
    folder: str
    cypnest: Optional[CypNestData]
    newerp: Optional[NewERPData]
    cut_length_diff_pct: float = 0
    parts_match: bool = True
    status: str = "OK"
    details: List[str] = field(default_factory=list)


def parse_cypnest_xlsx(xlsx_path: Path) -> Optional[CypNestData]:
    """Parsuj plik XLSX z wynikami CypNest"""
    try:
        xl = pd.ExcelFile(xlsx_path)

        data = CypNestData(
            source_file=xlsx_path.name,
            material="",
            thickness_mm=0,
            total_cut_length_m=0,
            total_cut_time_s=0,
            total_parts=0
        )

        # Parsuj All Parts List - naglowek w wierszu 1
        if 'All Parts List' in xl.sheet_names:
            df = pd.read_excel(xlsx_path, sheet_name='All Parts List', header=1)

            for _, row in df.iterrows():
                try:
                    # Nazwa detalu
                    name = str(row.get('Part Name', ''))
                    if not name or pd.isna(name) or name == 'nan':
                        continue

                    # Ilosc
                    qty_val = row.get('Qty', 1)
                    if pd.isna(qty_val):
                        qty_val = 1
                    qty = int(float(str(qty_val).replace(' ', '').split('/')[0].strip()) or 1)

                    # Wymiary z "Part Size(mm*mm)" np. "210.00 * 160.00"
                    size_str = str(row.get('Part Size(mm*mm)', '0 * 0'))
                    width, height = 0, 0
                    if '*' in size_str:
                        parts = size_str.split('*')
                        width = float(parts[0].strip())
                        height = float(parts[1].strip())

                    # Dlugosc ciecia z "Cut Length(m)"
                    cut_val = row.get('Cut Length(m)', 0)
                    if pd.isna(cut_val):
                        cut_val = 0
                    cut_length = float(cut_val)

                    data.parts.append(PartData(
                        name=name,
                        qty=qty,
                        width_mm=width,
                        height_mm=height,
                        cut_length_m=cut_length,
                        bbox_area_mm2=width * height
                    ))
                    data.total_parts += qty
                    data.total_cut_length_m += cut_length * qty
                except Exception as e:
                    pass

        # Parsuj Result sheets dla materialu i grubosci
        result_sheets = [s for s in xl.sheet_names if s.startswith('Result')]
        for sheet_name in result_sheets:
            df = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=None)

            # Szukaj materialu i grubosci (zwykle w wierszach 2-5)
            for i in range(min(10, len(df))):
                for j in range(min(8, len(df.columns))):
                    val = df.iloc[i, j]
                    if pd.isna(val):
                        continue
                    val_str = str(val)

                    # Material
                    if '1.4301' in val_str and not data.material:
                        data.material = '1.4301'
                    elif 'S235' in val_str and not data.material:
                        data.material = 'S235'
                    elif 'ST42' in val_str and not data.material:
                        data.material = 'ST42CrMo4'

                    # Grubosc (szukaj liczby w kolumnie Thickness)
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
        import traceback
        traceback.print_exc()
        return None


def parse_length(value: str) -> float:
    """Parsuj dlugosc z roznych formatow (m, mm, etc.)"""
    try:
        value = value.strip().lower()
        if 'm' in value and 'mm' not in value:
            # Metry
            num = float(value.replace('m', '').replace(',', '.').strip())
            return num
        elif 'mm' in value:
            # Milimetry -> metry
            num = float(value.replace('mm', '').replace(',', '.').strip())
            return num / 1000
        else:
            # Sprobuj jako liczbe
            num = float(value.replace(',', '.'))
            if num > 100:  # Pewnie mm
                return num / 1000
            return num
    except:
        return 0


def analyze_dxf_file(filepath: Path) -> Optional[PartData]:
    """Przeanalizuj pojedynczy plik DXF"""
    try:
        doc = ezdxf.readfile(str(filepath))
        msp = doc.modelspace()

        # Parsuj nazwe pliku
        name = filepath.stem
        qty = 1
        thickness = 0
        material = ""

        # Wyciagnij info z nazwy (np. "nazwa_2mm_INOX_3szt.dxf")
        parts = name.replace('-', '_').split('_')
        for p in parts:
            p_lower = p.lower()
            if 'szt' in p_lower:
                try:
                    qty = int(p_lower.replace('szt', '').strip())
                except:
                    pass
            if 'mm' in p_lower and thickness == 0:
                try:
                    thickness = float(p_lower.replace('mm', '').replace(',', '.').strip())
                except:
                    pass
            if 'inox' in p_lower or '1.4301' in p_lower:
                material = '1.4301'
            elif 's235' in p_lower or 'fe' in p_lower:
                material = 'S235'

        # Zbierz wszystkie encje do analizy
        IGNORE_LAYERS = {'AM_', 'RAMKA', 'WYMIARY', 'DIM', 'TEXT', 'DEFPOINTS'}

        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = float('-inf'), float('-inf')
        total_cut_length = 0
        contour_area = 0

        for entity in msp:
            layer = entity.dxf.layer.upper()
            if any(ign in layer for ign in IGNORE_LAYERS):
                continue

            etype = entity.dxftype()

            if etype == 'CIRCLE':
                cx, cy = entity.dxf.center.x, entity.dxf.center.y
                r = entity.dxf.radius
                min_x = min(min_x, cx - r)
                max_x = max(max_x, cx + r)
                min_y = min(min_y, cy - r)
                max_y = max(max_y, cy + r)
                total_cut_length += 2 * math.pi * r
                contour_area = max(contour_area, math.pi * r * r)

            elif etype == 'ARC':
                r = entity.dxf.radius
                sa, ea = entity.dxf.start_angle, entity.dxf.end_angle
                if ea < sa:
                    ea += 360
                arc_length = math.radians(ea - sa) * r
                total_cut_length += arc_length

            elif etype == 'LINE':
                p1 = entity.dxf.start
                p2 = entity.dxf.end
                min_x = min(min_x, p1.x, p2.x)
                max_x = max(max_x, p1.x, p2.x)
                min_y = min(min_y, p1.y, p2.y)
                max_y = max(max_y, p1.y, p2.y)
                length = math.sqrt((p2.x - p1.x)**2 + (p2.y - p1.y)**2)
                total_cut_length += length

            elif etype == 'LWPOLYLINE':
                # LWPOLYLINE moze miec bulge (luki) - format: (x, y, start_width, end_width, bulge)
                points_with_bulge = list(entity.get_points('xyb'))  # x, y, bulge
                points = [(p[0], p[1]) for p in points_with_bulge]
                bulges = [p[2] if len(p) > 2 else 0 for p in points_with_bulge]

                if points:
                    for px, py in points:
                        min_x = min(min_x, px)
                        max_x = max(max_x, px)
                        min_y = min(min_y, py)
                        max_y = max(max_y, py)

                    # Dlugosc z uwzglednieniem bulge
                    n_pts = len(points)
                    is_closed = entity.closed or (points[0] == points[-1])
                    for i in range(n_pts if is_closed else n_pts - 1):
                        p1 = points[i]
                        p2 = points[(i + 1) % n_pts]
                        bulge = bulges[i] if i < len(bulges) else 0

                        if bulge != 0:
                            # Arc segment
                            chord = math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
                            angle = 4 * math.atan(abs(bulge))
                            if angle > 0 and chord > 0:
                                radius = chord / (2 * math.sin(angle / 2))
                                arc_len = radius * angle
                                total_cut_length += arc_len
                        else:
                            # Line segment
                            length = math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
                            total_cut_length += length

                    # Powierzchnia (Shoelace) - przyblizenie
                    if is_closed:
                        area = 0
                        n = len(points)
                        for i in range(n):
                            j = (i + 1) % n
                            area += points[i][0] * points[j][1]
                            area -= points[j][0] * points[i][1]
                        contour_area = max(contour_area, abs(area) / 2)

            elif etype == 'POLYLINE':
                # Stary format POLYLINE (z wierzcholkami jako osobne encje)
                # Uwaga: POLYLINE moze miec bulge (luki)
                try:
                    vertices = list(entity.vertices)
                    points = [(v.dxf.location.x, v.dxf.location.y) for v in vertices]
                    bulges = [v.dxf.bulge if hasattr(v.dxf, 'bulge') else 0 for v in vertices]

                    if points:
                        for px, py in points:
                            min_x = min(min_x, px)
                            max_x = max(max_x, px)
                            min_y = min(min_y, py)
                            max_y = max(max_y, py)

                        # Dlugosc z uwzglednieniem bulge (lukow)
                        n_pts = len(points)
                        for i in range(n_pts if entity.is_closed else n_pts - 1):
                            p1 = points[i]
                            p2 = points[(i + 1) % n_pts]
                            bulge = bulges[i]

                            if bulge != 0:
                                # Arc segment - bulge = tan(angle/4)
                                chord = math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
                                angle = 4 * math.atan(abs(bulge))
                                if angle > 0 and chord > 0:
                                    radius = chord / (2 * math.sin(angle / 2))
                                    arc_len = radius * angle
                                    total_cut_length += arc_len
                            else:
                                # Line segment
                                length = math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
                                total_cut_length += length

                        # Powierzchnia (przyblizenie)
                        if entity.is_closed:
                            area = 0
                            n = len(points)
                            for i in range(n):
                                j = (i + 1) % n
                                area += points[i][0] * points[j][1]
                                area -= points[j][0] * points[i][1]
                            contour_area = max(contour_area, abs(area) / 2)
                except:
                    pass

        # Wymiary bbox
        width = max_x - min_x if max_x > min_x else 0
        height = max_y - min_y if max_y > min_y else 0

        if width <= 0 or height <= 0:
            return None

        # Fallback dla contour_area
        if contour_area <= 0:
            contour_area = width * height * 0.85  # Szacunek

        return PartData(
            name=name,
            qty=qty,
            width_mm=round(width, 2),
            height_mm=round(height, 2),
            cut_length_m=round(total_cut_length / 1000, 2),
            contour_area_mm2=round(contour_area, 0),
            bbox_area_mm2=round(width * height, 0),
            thickness_mm=thickness,
            material=material
        )

    except Exception as e:
        print(f"  Blad analizy DXF {filepath.name}: {e}")
        return None


def match_part_name(cypnest_name: str, dxf_name: str) -> bool:
    """Sprawdz czy nazwy pasuja (ignorujac roznice w formatowaniu)"""
    # Normalizuj nazwy
    cn = cypnest_name.lower().replace('-', '_').replace(' ', '_')
    dn = dxf_name.lower().replace('-', '_').replace(' ', '_')

    # Usun suffix _Xszt
    import re
    cn = re.sub(r'_\d+szt$', '', cn)
    dn = re.sub(r'_\d+szt$', '', dn)

    # Usun suffix mm
    cn = re.sub(r'_\d+[,.]?\d*mm', '', cn)
    dn = re.sub(r'_\d+[,.]?\d*mm', '', dn)

    # Usun material suffix
    for mat in ['_inox', '_fe', '_s235', '_st42']:
        cn = cn.replace(mat, '')
        dn = dn.replace(mat, '')

    return cn == dn or cn in dn or dn in cn


def analyze_folder(folder: Path) -> ComparisonResult:
    """Analizuj caly folder testowy"""
    result = ComparisonResult(folder=folder.name, cypnest=None, newerp=None)

    # 1. Parsuj XLSX (CypNest)
    xlsx_files = list(folder.glob('*.xlsx'))
    if xlsx_files:
        combined_cypnest = CypNestData(
            source_file=", ".join(f.name for f in xlsx_files),
            material="",
            thickness_mm=0,
            total_cut_length_m=0,
            total_cut_time_s=0,
            total_parts=0
        )

        for xlsx_file in xlsx_files:
            cypnest_data = parse_cypnest_xlsx(xlsx_file)
            if cypnest_data:
                combined_cypnest.total_cut_length_m += cypnest_data.total_cut_length_m
                combined_cypnest.total_parts += cypnest_data.total_parts
                combined_cypnest.parts.extend(cypnest_data.parts)
                if not combined_cypnest.material:
                    combined_cypnest.material = cypnest_data.material
                if combined_cypnest.thickness_mm == 0:
                    combined_cypnest.thickness_mm = cypnest_data.thickness_mm

        result.cypnest = combined_cypnest

    # 2. Analizuj DXF (NewERP)
    dxf_files = list(folder.glob('*.dxf'))
    if dxf_files:
        newerp_data = NewERPData(
            total_cut_length_m=0,
            total_parts=0
        )

        for dxf_file in dxf_files:
            part = analyze_dxf_file(dxf_file)
            if part:
                newerp_data.parts.append(part)

        # 3. Dopasuj ilosci z CypNest do DXF
        if result.cypnest:
            for newerp_part in newerp_data.parts:
                # Szukaj odpowiadajacego detalu w CypNest
                matched_qty = newerp_part.qty  # Domyslnie z nazwy pliku
                for cypnest_part in result.cypnest.parts:
                    if match_part_name(cypnest_part.name, newerp_part.name):
                        matched_qty = cypnest_part.qty
                        break

                newerp_part.qty = matched_qty
                newerp_data.total_parts += matched_qty
                newerp_data.total_cut_length_m += newerp_part.cut_length_m * matched_qty

        newerp_data.total_cut_length_m = round(newerp_data.total_cut_length_m, 2)
        result.newerp = newerp_data

    # 4. Porownaj wyniki
    if result.cypnest and result.newerp:
        if result.cypnest.total_cut_length_m > 0:
            diff = result.newerp.total_cut_length_m - result.cypnest.total_cut_length_m
            result.cut_length_diff_pct = round(diff / result.cypnest.total_cut_length_m * 100, 1)

        if abs(result.cut_length_diff_pct) <= 2:
            result.status = "OK"
        elif abs(result.cut_length_diff_pct) <= 5:
            result.status = "WARN"
        else:
            result.status = "FAIL"

        result.details.append(f"CypNest cut: {result.cypnest.total_cut_length_m:.2f}m")
        result.details.append(f"NewERP cut: {result.newerp.total_cut_length_m:.2f}m")
        result.details.append(f"Roznica: {result.cut_length_diff_pct:+.1f}%")
    else:
        result.status = "NO_DATA"
        if not result.cypnest:
            result.details.append("Brak danych CypNest (XLSX)")
        if not result.newerp:
            result.details.append("Brak danych NewERP (DXF)")

    return result


def generate_html_report(results: List[ComparisonResult], output_path: Path):
    """Generuj zbiorczy raport HTML"""

    html = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Raport Porownawczy NewERP vs CypNest - {datetime.now().strftime('%Y-%m-%d %H:%M')}</title>
    <style>
        :root {{
            --bg-dark: #0f0f0f;
            --bg-card: #1a1a1a;
            --text-primary: #ffffff;
            --text-secondary: #a0a0a0;
            --accent-primary: #8b5cf6;
            --accent-success: #22c55e;
            --accent-warning: #f59e0b;
            --accent-danger: #ef4444;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Segoe UI', sans-serif;
            background: var(--bg-dark);
            color: var(--text-primary);
            padding: 20px;
            line-height: 1.6;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{ color: var(--accent-primary); margin-bottom: 10px; }}
        h2 {{ color: var(--text-primary); margin: 30px 0 15px; border-bottom: 2px solid var(--accent-primary); padding-bottom: 10px; }}
        .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0; }}
        .summary-item {{ background: var(--bg-card); padding: 20px; border-radius: 8px; text-align: center; }}
        .summary-value {{ font-size: 2em; font-weight: bold; color: var(--accent-primary); }}
        .summary-label {{ color: var(--text-secondary); }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #333; }}
        th {{ background: #2d2d2d; color: var(--accent-primary); }}
        tr:hover {{ background: #2d2d2d; }}
        .status-ok {{ color: var(--accent-success); font-weight: bold; }}
        .status-warn {{ color: var(--accent-warning); font-weight: bold; }}
        .status-fail {{ color: var(--accent-danger); font-weight: bold; }}
        .number {{ text-align: right; font-family: monospace; }}
        .card {{ background: var(--bg-card); border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
        .diff-positive {{ color: var(--accent-danger); }}
        .diff-negative {{ color: var(--accent-success); }}
        .diff-neutral {{ color: var(--text-secondary); }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Raport Porownawczy NewERP vs CypNest</h1>
        <p style="color: var(--text-secondary);">Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

        <div class="summary">
            <div class="summary-item">
                <div class="summary-value">{len(results)}</div>
                <div class="summary-label">Folderow testowych</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{sum(1 for r in results if r.status == 'OK')}</div>
                <div class="summary-label">Passed (<=2%)</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{sum(1 for r in results if r.status == 'WARN')}</div>
                <div class="summary-label">Warning (2-5%)</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">{sum(1 for r in results if r.status in ['FAIL', 'NO_DATA'])}</div>
                <div class="summary-label">Failed (>5%)</div>
            </div>
        </div>

        <h2>Podsumowanie wynikow</h2>
        <table>
            <thead>
                <tr>
                    <th>Folder</th>
                    <th>Status</th>
                    <th class="number">CypNest [m]</th>
                    <th class="number">NewERP [m]</th>
                    <th class="number">Roznica</th>
                    <th>Detale</th>
                </tr>
            </thead>
            <tbody>
"""

    for r in results:
        status_class = f"status-{r.status.lower()}"
        cypnest_cut = f"{r.cypnest.total_cut_length_m:.2f}" if r.cypnest else "-"
        newerp_cut = f"{r.newerp.total_cut_length_m:.2f}" if r.newerp else "-"

        diff_class = "diff-neutral"
        if r.cut_length_diff_pct > 2:
            diff_class = "diff-positive"
        elif r.cut_length_diff_pct < -2:
            diff_class = "diff-negative"

        diff_str = f"{r.cut_length_diff_pct:+.1f}%" if r.cypnest and r.newerp else "-"

        html += f"""
                <tr>
                    <td><strong>{r.folder}</strong></td>
                    <td class="{status_class}">{r.status}</td>
                    <td class="number">{cypnest_cut}</td>
                    <td class="number">{newerp_cut}</td>
                    <td class="number {diff_class}">{diff_str}</td>
                    <td>{'; '.join(r.details[:2])}</td>
                </tr>
"""

    html += """
            </tbody>
        </table>

        <h2>Szczegoly dla kazdego folderu</h2>
"""

    for r in results:
        status_class = f"status-{r.status.lower()}"
        html += f"""
        <div class="card">
            <h3 style="color: var(--accent-primary);">{r.folder} <span class="{status_class}">({r.status})</span></h3>
"""

        if r.newerp and r.newerp.parts:
            html += """
            <h4 style="margin-top: 15px;">Detale (NewERP):</h4>
            <table>
                <thead>
                    <tr>
                        <th>Nazwa</th>
                        <th class="number">Qty</th>
                        <th class="number">Wymiary [mm]</th>
                        <th class="number">Cut [m]</th>
                        <th class="number">Contour [mm2]</th>
                    </tr>
                </thead>
                <tbody>
"""
            for part in r.newerp.parts:
                html += f"""
                    <tr>
                        <td>{part.name[:40]}{'...' if len(part.name) > 40 else ''}</td>
                        <td class="number">{part.qty}</td>
                        <td class="number">{part.width_mm:.1f} x {part.height_mm:.1f}</td>
                        <td class="number">{part.cut_length_m:.2f}</td>
                        <td class="number">{part.contour_area_mm2:,.0f}</td>
                    </tr>
"""
            html += """
                </tbody>
            </table>
"""

        html += """
        </div>
"""

    html += """
    </div>
</body>
</html>
"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\nRaport HTML zapisany: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Zbiorczy raport porownawczy NewERP vs CypNest")
    parser.add_argument("--folders", type=str, nargs='+',
                       default=['Test1', 'test2', 'Test3', 'Test4', 'Test5', 'Test6'],
                       help="Lista folderow do analizy")
    parser.add_argument("--base-path", type=str, default="C:/temp",
                       help="Sciezka bazowa do folderow")
    parser.add_argument("--output", type=str, default="C:/temp/comparison_report.html",
                       help="Sciezka do raportu HTML")
    args = parser.parse_args()

    print("=" * 60)
    print("  ZBIORCZY RAPORT POROWNAWCZY NewERP vs CypNest")
    print("=" * 60)

    results = []

    for folder_name in args.folders:
        folder = Path(args.base_path) / folder_name
        if folder.exists():
            print(f"\nAnalizuje: {folder_name}...")
            result = analyze_folder(folder)
            results.append(result)

            status_icon = {"OK": "[OK]", "WARN": "[!!]", "FAIL": "[XX]", "NO_DATA": "[--]"}
            print(f"  {status_icon.get(result.status, '[??]')} {result.status}: {', '.join(result.details)}")
        else:
            print(f"\n{folder_name}: folder nie istnieje")

    # Generuj raport HTML
    if results:
        generate_html_report(results, Path(args.output))

    # Podsumowanie
    print("\n" + "=" * 60)
    print("  PODSUMOWANIE")
    print("=" * 60)
    ok_count = sum(1 for r in results if r.status == 'OK')
    warn_count = sum(1 for r in results if r.status == 'WARN')
    fail_count = sum(1 for r in results if r.status in ['FAIL', 'NO_DATA'])
    print(f"  OK (<=2%):     {ok_count}")
    print(f"  WARN (2-5%):   {warn_count}")
    print(f"  FAIL (>5%):    {fail_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
