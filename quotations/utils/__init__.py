"""
Quotations Utils
================
Narzędzia pomocnicze dla modułu wycen.
- dxf_loader: Wczytywanie plików DXF
- dxf_thumbnail: Generowanie miniaturek
- name_parser: Parser nazw plików (materiał, grubość, ilość)
"""

from .dxf_thumbnail import (
    generate_thumbnail,
    get_dxf_thumbnail,
    get_dxf_thumbnail_simple,
    can_generate_thumbnails,
    clear_thumbnail_cache
)

from .dxf_loader import DXFPart, load_dxf, load_dxf_as_path

from .name_parser import (
    parse_filename, parse_filename_with_folder_context,
    find_material, find_thickness, find_quantity,
    reload_rules, get_rules_as_list, save_rules_to_json,
    normalize_material, MATERIAL_ALIASES
)

__all__ = [
    # Thumbnails
    'generate_thumbnail',
    'get_dxf_thumbnail',
    'get_dxf_thumbnail_simple',
    'can_generate_thumbnails',
    'clear_thumbnail_cache',
    # DXF Loader
    'DXFPart', 'load_dxf', 'load_dxf_as_path',
    # Name Parser
    'parse_filename', 'parse_filename_with_folder_context',
    'find_material', 'find_thickness', 'find_quantity',
    'reload_rules', 'get_rules_as_list', 'save_rules_to_json',
    'normalize_material', 'MATERIAL_ALIASES'
]
