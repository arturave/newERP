# -*- coding: utf-8 -*-
"""
name_parser.py
==============
Rule-based parser loading definitions from regex_rules.json.
Parsuje nazwy plików DXF aby wyciągnąć materiał, grubość i ilość.
"""
from __future__ import annotations

import os
import re
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# Domyślna lokalizacja pliku reguł
DEFAULT_RULES_FILE = Path(__file__).parent.parent.parent / "config" / "regex_rules.json"

_TOKEN_LEFT = r"(?:^|[_\-\s\.,\(\)\[\]\{\}])"
_TOKEN_RIGHT = r"(?:$|[_\-\s\.,\(\)\[\]\{\}])"
_SEP_CHARS = r"[_\-\s\.,\(\)\[\]\{\}]+"


@dataclass(frozen=True)
class MaterialPattern:
    """Wzorzec materiału"""
    regex: re.Pattern
    label: str
    priority: int


# Globalna lista wzorców (ładowana dynamicznie)
MATERIAL_PATTERNS: List[MaterialPattern] = []
_rules_file_path: Optional[Path] = None

# Mapowanie aliasów materiałów na nazwy standardowe
# Jeśli wykryty materiał znajduje się w tym słowniku, zostanie zamieniony na wartość
MATERIAL_ALIASES: Dict[str, str] = {
    "1.4301 (Generic)": "1.4301",
    "1.4401 (Generic)": "1.4401",
    "1.4404 (Generic)": "1.4404",
    "INOX": "1.4301",
    "inox": "1.4301",
    "Inox": "1.4301",
    "STAL": "S235",
    "Stal": "S235",
    "stal": "S235",
}


def normalize_material(material: str) -> str:
    """
    Normalizuj nazwę materiału używając słownika aliasów.
    Jeśli materiał jest w słowniku aliasów, zwróć wartość standardową.
    """
    if not material:
        return material
    return MATERIAL_ALIASES.get(material, material)


def _safe_compile(pattern: str) -> re.Pattern:
    """Bezpieczna kompilacja regex"""
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        logger.error(f"Invalid regex '{pattern}': {e}")
        # Zwracamy bezpieczny pattern, który nic nie dopasuje
        return re.compile(r"(?!x)x")


def get_rules_file_path() -> Path:
    """Zwróć aktualną ścieżkę do pliku reguł"""
    global _rules_file_path
    if _rules_file_path:
        return _rules_file_path
    return DEFAULT_RULES_FILE


def set_rules_file_path(filepath: Path) -> None:
    """Ustaw ścieżkę do pliku reguł"""
    global _rules_file_path
    _rules_file_path = filepath
    load_rules_from_json(filepath)


def load_rules_from_json(filepath: Optional[Path] = None) -> None:
    """Ładuje reguły z pliku JSON i kompiluje je do MATERIAL_PATTERNS."""
    global MATERIAL_PATTERNS, _rules_file_path
    MATERIAL_PATTERNS.clear()
    
    if filepath is None:
        filepath = get_rules_file_path()
    else:
        _rules_file_path = filepath
    
    if not filepath.exists():
        logger.warning(f"Rules file {filepath} not found. Using built-in patterns.")
        _load_builtin_patterns()
        return

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            raise ValueError("JSON root must be a list")

        for priority, item in enumerate(data):
            label = item.get("name", "Unknown")
            aliases = item.get("aliases", [])
            
            for alias in aliases:
                # Automatycznie dodajemy granice słów/tokenów
                clean_p = alias.replace(r"\b", "")
                regex_str = f"{_TOKEN_LEFT}(?:{clean_p}){_TOKEN_RIGHT}"
                
                pat = MaterialPattern(
                    regex=_safe_compile(regex_str),
                    label=label,
                    priority=priority
                )
                MATERIAL_PATTERNS.append(pat)
                
        logger.info(f"Loaded {len(MATERIAL_PATTERNS)} patterns from {filepath}")
        
    except Exception as e:
        logger.error(f"Failed to load rules from JSON: {e}")
        _load_builtin_patterns()


def _load_builtin_patterns() -> None:
    """Załaduj wbudowane wzorce (fallback)"""
    global MATERIAL_PATTERNS
    
    builtin = [
        ("1.4404", ["1[.,]?4404", "316l", "aisi[_ ]?316l"]),
        ("1.4401", ["1[.,]?4401", "aisi[_ ]?316", "inox\\s*316", "\\b316\\b"]),
        ("1.4301", ["1[.,]?4301", "aisi[_ ]?304", "inox\\s*304", "\\b304\\b", "nerez"]),
        ("1.4301 (Generic)", ["inox"]),
        ("S355", ["s355", "s355jr", "s355j2", "s355mc"]),
        ("S235", ["s235", "s235jr", "fe\\s*360", "\\bfe\\b"]),
        ("ALUMINIUM", ["aluminium", "\\balu\\b", "alu[_ -]?6060", "\\bal\\b"]),
        ("DC01", ["dc01", "dc-01"]),
        ("Corten", ["corten", "cor[- ]?ten"]),
        ("42CrMo4", ["42crmo4", "42c.?m0?4"]),
    ]
    
    for priority, (label, aliases) in enumerate(builtin):
        for alias in aliases:
            regex_str = f"{_TOKEN_LEFT}(?:{alias}){_TOKEN_RIGHT}"
            pat = MaterialPattern(
                regex=_safe_compile(regex_str),
                label=label,
                priority=priority
            )
            MATERIAL_PATTERNS.append(pat)
    
    logger.info(f"Loaded {len(MATERIAL_PATTERNS)} built-in patterns")


def reload_rules() -> None:
    """Odśwież reguły z pliku"""
    load_rules_from_json()


def save_rules_to_json(rules: List[Dict[str, Any]], filepath: Optional[Path] = None) -> bool:
    """Zapisz reguły do pliku JSON"""
    if filepath is None:
        filepath = get_rules_file_path()
    
    try:
        # Upewnij się że katalog istnieje
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(rules, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved {len(rules)} rules to {filepath}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save rules: {e}")
        return False


def get_rules_as_list() -> List[Dict[str, Any]]:
    """Pobierz aktualne reguły jako listę słowników"""
    filepath = get_rules_file_path()
    
    if not filepath.exists():
        return []
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read rules: {e}")
        return []


def _normalize_decimal(num_str: str) -> str:
    """Normalizuj separator dziesiętny"""
    return num_str.replace(",", ".").strip()


def find_thickness(text: str) -> Tuple[Optional[float], Optional[Tuple[int, int]]]:
    """
    Znajdź grubość w tekście.
    
    Rozpoznaje formaty:
    - 3mm, 3.5mm, 3,5mm
    - #3, #3.5
    - gr3, gr.3, gr 3
    
    Returns:
        (grubość w mm, span dopasowania) lub (None, None)
    """
    # Format: Xmm (bez X jako wymiar np. 100x200)
    pat_mm = re.compile(rf"(?<![xX×])(?<![\d.,])#?\s*(\d+(?:[.,]\d+)?)\s*mm{_TOKEN_RIGHT}", re.IGNORECASE)
    m = pat_mm.search(text)
    if m:
        try:
            val = float(_normalize_decimal(m.group(1)))
            if 0.0 < val <= 200.0:
                return val, m.span()
        except ValueError:
            pass

    # Format: #X (hash + liczba)
    pat_hash = re.compile(rf"{_TOKEN_LEFT}#\s*(\d+(?:[.,]\d+)?){_TOKEN_RIGHT}", re.IGNORECASE)
    m = pat_hash.search(text)
    if m:
        try:
            val = float(_normalize_decimal(m.group(1)))
            if 0.0 < val <= 200.0:
                return val, m.span()
        except ValueError:
            pass

    # Format: grX, gr.X, gr X
    pat_gr = re.compile(rf"{_TOKEN_LEFT}gr\.?\s*(\d+(?:[.,]\d+)?){_TOKEN_RIGHT}", re.IGNORECASE)
    m = pat_gr.search(text)
    if m:
        try:
            val = float(_normalize_decimal(m.group(1)))
            if 0.0 < val <= 200.0:
                return val, m.span()
        except ValueError:
            pass

    return None, None


def find_quantity(text: str) -> Tuple[Optional[int], Optional[Tuple[int, int]]]:
    """
    Znajdź ilość w tekście.
    
    Rozpoznaje formaty:
    - 10szt, 10 szt, 10szt.
    - szt:10, szt.10, szt 10
    - 10pcs, 10pc, 10ks
    
    Returns:
        (ilość, span dopasowania) lub (None, None)
    """
    # Format: Xszt (liczba przed jednostką)
    pat1 = re.compile(rf"(?<!\d)(\d{{1,5}})\s*[:\-]?\s*(szt\.?|pcs|pc|ks|st){_TOKEN_RIGHT}", re.IGNORECASE)
    m = pat1.search(text)
    if m:
        try:
            return int(m.group(1)), m.span()
        except ValueError:
            pass

    # Format: szt:X (jednostka przed liczbą)
    pat2 = re.compile(rf"{_TOKEN_LEFT}(szt\.?|pcs|pc|ks|st)\s*[:\-]?\s*(\d{{1,5}}){_TOKEN_RIGHT}", re.IGNORECASE)
    m = pat2.search(text)
    if m:
        try:
            return int(m.group(2)), m.span()
        except ValueError:
            pass

    return None, None


def find_material(text: str) -> Tuple[str, Optional[Tuple[int, int]], Optional[str]]:
    """
    Znajduje materiał w oparciu o załadowane wzorce.
    Priorytet: Kolejność w pliku JSON (im wyżej, tym ważniejszy).
    
    Returns:
        (label materiału, span dopasowania, pattern) lub ("", None, None)
    """
    candidates = []

    for mp in MATERIAL_PATTERNS:
        for m in mp.regex.finditer(text):
            candidates.append({
                "label": mp.label,
                "span": m.span(),
                "pattern": mp.regex.pattern,
                "priority": mp.priority,
                "start": m.start()
            })

    if not candidates:
        return "", None, None

    # Sortowanie: 1. Priorytet (rosnąco), 2. Pozycja startowa, 3. Długość dopasowania (malejąco)
    candidates.sort(key=lambda x: (x["priority"], x["start"], -(x["span"][1] - x["span"][0])))

    best = candidates[0]
    return best["label"], best["span"], best["pattern"]


def compute_core_name(stem: str, spans: List[Optional[Tuple[int, int]]]) -> str:
    """Oblicz nazwę bazową (bez materiału, grubości, ilości)"""
    starts = [sp[0] for sp in spans if sp is not None]
    core_raw = stem[: min(starts)] if starts else stem
    core_raw = re.sub(rf"{_SEP_CHARS}$", "", core_raw)
    core_raw = re.sub(r"(_\d+)$", "", core_raw)
    return core_raw.strip()


def parse_text(text: str) -> Dict[str, Optional[object]]:
    """
    Parsuj tekst i wyciągnij informacje.
    
    Returns:
        Dict z kluczami: core_name, material, thickness_mm, quantity, debug
    """
    stem = text
    thickness, span_th = find_thickness(stem)
    quantity, span_q = find_quantity(stem)
    material, span_mat, _ = find_material(stem)
    
    # Normalizuj materiał (zamień aliasy na standardowe nazwy)
    material = normalize_material(material) if material else ""
    
    core_name = compute_core_name(stem, [span_th, span_q, span_mat])

    return {
        "core_name": core_name,
        "material": material,
        "thickness_mm": thickness,
        "quantity": quantity,
        "debug": {
            "span_thickness": span_th,
            "span_quantity": span_q,
            "span_material": span_mat,
        },
    }


def parse_filename(filename: str) -> Dict[str, Optional[object]]:
    """Parsuj nazwę pliku (bez rozszerzenia)"""
    stem, _ = os.path.splitext(filename)
    return parse_text(stem)


def parse_filename_with_folder_context(file_path: Path, stop_at: Optional[Path] = None) -> Dict[str, Optional[object]]:
    """
    Parsuj nazwę pliku z kontekstem folderów nadrzędnych.
    Jeśli brakuje materiału lub grubości w nazwie, szuka w nazwach folderów.
    
    Args:
        file_path: Ścieżka do pliku
        stop_at: Opcjonalny folder, przy którym przestać szukać
    
    Returns:
        Dict z danymi (jak parse_filename, ale z uzupełnionymi brakami z folderów)
    """
    raw = parse_filename(file_path.name)
    need_thickness = raw.get("thickness_mm") is None
    need_material = not (raw.get("material") or "").strip()

    if not (need_thickness or need_material):
        return raw

    cur = file_path.parent
    stop_at = stop_at.resolve() if stop_at else None

    while True:
        ctx = parse_text(cur.name)
        if need_thickness and ctx.get("thickness_mm") is not None:
            raw["thickness_mm"] = ctx["thickness_mm"]
            need_thickness = False
        if need_material and (ctx.get("material") or "").strip():
            raw["material"] = ctx["material"]
            need_material = False
        
        if not (need_thickness or need_material):
            break
        if stop_at and cur.resolve() == stop_at:
            break
        if cur.parent == cur:
            break
        cur = cur.parent

    # Końcowa normalizacja materiału (na wypadek gdyby był uzupełniony z folderu)
    if raw.get("material"):
        raw["material"] = normalize_material(raw["material"])
    
    return raw


# Inicjalne ładowanie przy starcie modułu
load_rules_from_json()


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":
    import sys
    
    test_names = [
        "11-066253_INOX_3mm_79szt.dxf",
        "Kątownik_S355_5mm_10szt.dxf",
        "PŁYTA_DC01_gr2.dxf",
        "wspornik_alu_#4_szt15.dxf",
        "frame_316L_8mm_pcs5.dxf",
    ]
    
    if len(sys.argv) > 1:
        test_names = sys.argv[1:]
    
    print("=" * 60)
    print("NAME PARSER TEST")
    print("=" * 60)
    
    for name in test_names:
        result = parse_filename(name)
        print(f"\n{name}")
        print(f"  Core name: {result['core_name']}")
        print(f"  Material:  {result['material'] or 'NOT FOUND'}")
        print(f"  Thickness: {result['thickness_mm'] or 'NOT FOUND'} mm")
        print(f"  Quantity:  {result['quantity'] or 'NOT FOUND'}")
