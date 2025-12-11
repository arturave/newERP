"""
DXF Layer Filters - Filtrowanie warstw DXF
==========================================
Definicje warstw do ignorowania, warstw konturu zewnętrznego i otworów.
"""

from typing import Set, List, Optional

# Warstwy do ignorowania (nie są cięte)
IGNORE_LAYERS: Set[str] = {
    # Wymiary i tekst
    "RAMKA", "WYMIARY", "DIM", "TEXT", "TEKST", "OPIS", "DEFPOINTS",
    # Struktura i ukryte
    "ASSEMBLY", "HIDDEN", "CENTER", "CUTLINE", "GRID", "TITLE",
    "BLOCK", "LOGO", "INFO", "FRAME", "BORDER",
    # Inventor specjalne
    "AM_",           # Wszystkie warstwy AM_ (Autodesk Mechanical)
    "IV_ARC_CENTERS", # Środki łuków - pomocnicze
    # Inne CAD
    "0_NOTES", "ANNOTATIONS", "DIMS", "SYMBOLS",
}

# Słowa kluczowe w nazwach warstw do ignorowania
IGNORE_KEYWORDS: Set[str] = {
    "WYMIAR", "DIM", "TEXT", "FRAME", "BORDER", "NOTE", "ANNO",
    "HIDDEN", "CENTER", "GRID", "TITLE", "LOGO", "INFO",
}

# Warstwy preferowane dla konturu zewnętrznego (kolejność = priorytet)
OUTER_LAYERS: List[str] = [
    'IV_OUTER_PROFILE',  # Inventor - profil zewnętrzny
    'OUTER',
    'KONTUR',
    'OUTLINE',
    'CONTOUR',
    'EXTERNAL',
    'PROFILE',
    '0',                 # Domyślna warstwa
    '2',
    'Domyślne',
]

# Warstwy dla otworów (kontury wewnętrzne)
INNER_LAYERS: List[str] = [
    'IV_INTERIOR_PROFILES',  # Inventor - profile wewnętrzne
    'INNER',
    'OTWORY',
    'HOLES',
    'INTERIOR',
    'INTERNAL',
    'CUTOUTS',
]

# Warstwy dla cech specjalnych (bend relief, etc.)
FEATURE_LAYERS: List[str] = [
    'IV_FEATURE_PROFILES',  # Inventor - cechy (relief cuts = ARCs, bend lines = LINEs)
]

# Słowa kluczowe dla warstw grawerowania
MARKING_KEYWORDS: Set[str] = {
    'MARK', 'MARKING', 'ENGRAV', 'GRAWER', 'ETCH', 'LASER_MARK',
}

# Słowa kluczowe dla warstw gięcia
BENDING_KEYWORDS: Set[str] = {
    'BEND', 'FOLD', 'GIECIE', 'ZGINANIE', 'CREASE',
}


def is_ignored_layer(layer_name: str) -> bool:
    """
    Sprawdź czy warstwa powinna być ignorowana.

    Args:
        layer_name: Nazwa warstwy

    Returns:
        True jeśli warstwa powinna być ignorowana
    """
    if not layer_name:
        return False

    layer_upper = layer_name.upper()

    # Sprawdź dokładne dopasowanie
    if layer_upper in IGNORE_LAYERS:
        return True

    # Sprawdź słowa kluczowe
    for keyword in IGNORE_KEYWORDS:
        if keyword in layer_upper:
            return True

    # Sprawdź prefiks AM_ (Autodesk Mechanical)
    if layer_upper.startswith('AM_'):
        return True

    return False


def is_outer_layer(layer_name: str) -> bool:
    """Sprawdź czy to warstwa konturu zewnętrznego"""
    if not layer_name:
        return False

    layer_upper = layer_name.upper()

    for outer in OUTER_LAYERS:
        if layer_upper == outer.upper():
            return True

    return False


def is_inner_layer(layer_name: str) -> bool:
    """Sprawdź czy to warstwa otworów"""
    if not layer_name:
        return False

    layer_upper = layer_name.upper()

    for inner in INNER_LAYERS:
        if layer_upper == inner.upper():
            return True

    return False


def is_feature_layer(layer_name: str) -> bool:
    """Sprawdź czy to warstwa cech specjalnych"""
    if not layer_name:
        return False

    layer_upper = layer_name.upper()

    for feature in FEATURE_LAYERS:
        if feature.upper() in layer_upper:
            return True

    return False


def is_marking_layer(layer_name: str) -> bool:
    """Sprawdź czy to warstwa grawerowania"""
    if not layer_name:
        return False

    layer_upper = layer_name.upper()

    for keyword in MARKING_KEYWORDS:
        if keyword in layer_upper:
            return True

    return False


def is_bending_layer(layer_name: str) -> bool:
    """Sprawdź czy to warstwa gięcia"""
    if not layer_name:
        return False

    layer_upper = layer_name.upper()

    for keyword in BENDING_KEYWORDS:
        if keyword in layer_upper:
            return True

    return False


def get_layer_priority(layer_name: str) -> int:
    """
    Pobierz priorytet warstwy dla konturu zewnętrznego.
    Niższy = wyższy priorytet.

    Args:
        layer_name: Nazwa warstwy

    Returns:
        Priorytet (0-999, 999 = najniższy)
    """
    if not layer_name:
        return 999

    layer_upper = layer_name.upper()

    for i, outer in enumerate(OUTER_LAYERS):
        if layer_upper == outer.upper():
            return i

    return 999


def classify_layer(layer_name: str) -> str:
    """
    Klasyfikuj warstwę.

    Args:
        layer_name: Nazwa warstwy

    Returns:
        Jedna z: 'ignore', 'outer', 'inner', 'feature', 'marking', 'bending', 'unknown'
    """
    if is_ignored_layer(layer_name):
        return 'ignore'
    if is_outer_layer(layer_name):
        return 'outer'
    if is_inner_layer(layer_name):
        return 'inner'
    if is_feature_layer(layer_name):
        return 'feature'
    if is_marking_layer(layer_name):
        return 'marking'
    if is_bending_layer(layer_name):
        return 'bending'
    return 'unknown'


# Eksporty
__all__ = [
    'IGNORE_LAYERS',
    'IGNORE_KEYWORDS',
    'OUTER_LAYERS',
    'INNER_LAYERS',
    'FEATURE_LAYERS',
    'MARKING_KEYWORDS',
    'BENDING_KEYWORDS',
    'is_ignored_layer',
    'is_outer_layer',
    'is_inner_layer',
    'is_feature_layer',
    'is_marking_layer',
    'is_bending_layer',
    'get_layer_priority',
    'classify_layer',
]
