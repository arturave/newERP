# -*- coding: utf-8 -*-
"""
name_parser.py
Rule-based parser loading definitions from regex_rules.json.
"""
from __future__ import annotations

import os
import re
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Konfiguracja - ścieżka względem tego pliku
_THIS_DIR = Path(__file__).parent
RULES_FILE = _THIS_DIR / "regex_rules.json"
_TOKEN_LEFT = r"(?:^|[_\-\s\.,\(\)\[\]\{\}])"
_TOKEN_RIGHT = r"(?:$|[_\-\s\.,\(\)\[\]\{\}])"
_SEP_CHARS = r"[_\-\s\.,\(\)\[\]\{\}]+"

log = logging.getLogger("name_parser")

@dataclass(frozen=True)
class MaterialPattern:
    regex: re.Pattern
    label: str
    priority: int

# Globalna lista wzorców (ładowana dynamicznie)
MATERIAL_PATTERNS: List[MaterialPattern] = []

def _safe_compile(pattern: str) -> re.Pattern:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        log.error(f"Invalid regex '{pattern}': {e}")
        # Zwracamy bezpieczny pattern, który nic nie dopasuje, żeby nie wywalić apki
        return re.compile(r"(?!x)x")

def load_rules_from_json(filepath: Path = RULES_FILE) -> None:
    """Ładuje reguły z pliku JSON i kompiluje je do MATERIAL_PATTERNS."""
    global MATERIAL_PATTERNS
    MATERIAL_PATTERNS.clear()
    
    if not filepath.exists():
        log.warning(f"Rules file {filepath} not found. Parsing will be limited.")
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
                # Automatycznie dodajemy granice słów/tokenów, jak w poprzedniej wersji
                clean_p = alias.replace(r"\b", "") # usuwamy \b jeśli ktoś wpisał ręcznie, bo dodajemy własne
                # Jeśli alias zawiera już skomplikowane regexy, ufamy użytkownikowi,
                # ale standardowo opakowujemy w token boundaries
                regex_str = f"{_TOKEN_LEFT}(?:{clean_p}){_TOKEN_RIGHT}"
                
                pat = MaterialPattern(
                    regex=_safe_compile(regex_str),
                    label=label,
                    priority=priority
                )
                MATERIAL_PATTERNS.append(pat)
                
        log.info(f"Loaded {len(MATERIAL_PATTERNS)} patterns from {filepath}")
        
    except Exception as e:
        log.error(f"Failed to load rules from JSON: {e}")

# Inicjalne ładowanie przy starcie modułu
load_rules_from_json()

def reload_rules():
    """Funkcja pomocnicza do odświeżania reguł (np. po edycji w GUI)."""
    load_rules_from_json()

def _normalize_decimal(num_str: str) -> str:
    return num_str.replace(",", ".").strip()

def find_thickness(text: str) -> Tuple[Optional[float], Optional[Tuple[int, int]]]:
    # Pattern dla "0,5mm", "2mm", "- 3mm -" itp.
    # Pozwala na spacje i separatory przed liczbą
    pat_mm = re.compile(r"(?:^|[_\-\s])(\d+(?:[.,]\d+)?)\s*mm(?:$|[_\-\s\.])", re.IGNORECASE)
    m = pat_mm.search(text)
    if m:
        try:
            val = float(_normalize_decimal(m.group(1)))
            if 0.0 < val <= 200.0:
                return val, m.span()
        except ValueError:
            pass
    
    # Alternatywny pattern z "mm" na końcu
    pat_mm2 = re.compile(r"(\d+(?:[.,]\d+)?)\s*mm", re.IGNORECASE)
    m = pat_mm2.search(text)
    if m:
        try:
            val = float(_normalize_decimal(m.group(1)))
            if 0.0 < val <= 200.0:
                return val, m.span()
        except ValueError:
            pass

    pat_hash = re.compile(rf"{_TOKEN_LEFT}#\s*(\d+(?:[.,]\d+)?){_TOKEN_RIGHT}", re.IGNORECASE)
    m = pat_hash.search(text)
    if m:
        try:
            val = float(_normalize_decimal(m.group(1)))
            if 0.0 < val <= 200.0:
                return val, m.span()
        except ValueError:
            pass

    return None, None

def find_quantity(text: str) -> Tuple[Optional[int], Optional[Tuple[int, int]]]:
    pat1 = re.compile(rf"(?<!\d)(\d{{1,5}})\s*[:\-]?\s*(szt\.?|pcs|pc|ks|st){_TOKEN_RIGHT}", re.IGNORECASE)
    m = pat1.search(text)
    if m:
        try:
            return int(m.group(1)), m.span()
        except ValueError:
            pass

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
    starts = [sp[0] for sp in spans if sp is not None]
    core_raw = stem[: min(starts)] if starts else stem
    core_raw = re.sub(rf"{_SEP_CHARS}$", "", core_raw)
    core_raw = re.sub(r"(_\d+)$", "", core_raw)
    return core_raw.strip()

def parse_text(text: str) -> Dict[str, Optional[object]]:
    stem = text
    thickness, span_th = find_thickness(stem)
    quantity, span_q = find_quantity(stem)
    material, span_mat, _ = find_material(stem)
    core_name = compute_core_name(stem, [span_th, span_q, span_mat])

    return {
        "core_name": core_name,
        "material": material or "",
        "thickness_mm": thickness,
        "quantity": quantity,
        "debug": {
            "span_thickness": span_th,
            "span_quantity": span_q,
            "span_material": span_mat,
        },
    }

def parse_filename(filename: str) -> Dict[str, Optional[object]]:
    stem, _ = os.path.splitext(filename)
    return parse_text(stem)

def parse_filename_with_folder_context(file_path: Path, stop_at: Optional[Path] = None) -> Dict[str, Optional[object]]:
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

    return raw
    