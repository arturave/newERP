#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Products Utils - Narzędzia pomocnicze

Komponenty:
- ThumbnailGenerator: Generowanie miniatur i analiza wymiarów z plików CAD
- CompressionManager: Kompresja plików CAD (gzip/bundle)

Obsługiwane formaty ThumbnailGenerator:
- 2D: DXF, DWG (wymaga ezdxf + matplotlib)
- 3D: STEP, STP, IGES, IGS (wymaga CadQuery + VTK)
- Mesh: STL, OBJ (wymaga VTK)
- Obrazy: PNG, JPG, BMP, GIF, WEBP, TIFF

Strategie kompresji:
- NONE: bez kompresji
- INDIVIDUAL: każdy plik CAD skompresowany osobno (.gz)
- BUNDLE: wszystkie pliki w jednym archiwum (.zip)
- HYBRID: CAD i źródła w .gz, miniatury bez kompresji (ZALECANE)

Użycie:
    from products.utils import ThumbnailGenerator, CompressionManager
    
    # Miniatury
    gen = ThumbnailGenerator()
    thumbs = gen.generate(file_bytes, 'dxf')
    
    # Kompresja
    comp = CompressionManager()
    result = comp.compress(file_bytes, 'model.step')
"""

from products.utils.thumbnail_generator import (
    ThumbnailGenerator,
    create_thumbnail_generator
)

from products.utils.compression import (
    CompressionManager,
    CompressionStrategy,
    CompressionResult,
    create_compression_manager,
    compress_file,
    decompress_file,
    get_compression_stats
)

__all__ = [
    # Thumbnails
    'ThumbnailGenerator',
    'create_thumbnail_generator',
    # Compression
    'CompressionManager',
    'CompressionStrategy',
    'CompressionResult',
    'create_compression_manager',
    'compress_file',
    'decompress_file',
    'get_compression_stats',
]
