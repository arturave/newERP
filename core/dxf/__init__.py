"""
Core DXF Module - Unified DXF Reading and Processing
=====================================================

Centralne narzędzia do odczytu i przetwarzania plików DXF.

Główne komponenty:
- UnifiedDXFReader: Centralny reader plików DXF
- DXFPart: Kompletny detal z geometrią
- DXFContour: Zamknięty kontur (zewnętrzny lub otwór)
- DXFEntity: Pojedyncza entity DXF

Użycie:
    from core.dxf import UnifiedDXFReader

    reader = UnifiedDXFReader()
    part = reader.read("path/to/file.dxf")

    print(f"Wymiary: {part.width:.1f} x {part.height:.1f} mm")
    print(f"Pole: {part.contour_area:.1f} mm²")
"""

from .entities import (
    EntityType,
    DXFEntity,
    DXFContour,
    DXFDimension,
    LayerInfo,
    DXFPart,
)

from .converters import (
    arc_to_points,
    circle_to_points,
    bulge_arc_to_points,
    convert_entity,
    HAS_EZDXF,
)

from .contour_builder import (
    ContourBuilder,
    build_contours_from_entities,
)

from .layer_filters import (
    IGNORE_LAYERS,
    OUTER_LAYERS,
    INNER_LAYERS,
    is_ignored_layer,
    is_outer_layer,
    is_inner_layer,
    classify_layer,
)

from .reader import (
    UnifiedDXFReader,
    load_dxf,
)


__all__ = [
    # Entities
    'EntityType',
    'DXFEntity',
    'DXFContour',
    'DXFDimension',
    'LayerInfo',
    'DXFPart',

    # Converters
    'arc_to_points',
    'circle_to_points',
    'bulge_arc_to_points',
    'convert_entity',
    'HAS_EZDXF',

    # Contour Builder
    'ContourBuilder',
    'build_contours_from_entities',

    # Layer Filters
    'IGNORE_LAYERS',
    'OUTER_LAYERS',
    'INNER_LAYERS',
    'is_ignored_layer',
    'is_outer_layer',
    'is_inner_layer',
    'classify_layer',

    # Reader
    'UnifiedDXFReader',
    'load_dxf',
]
