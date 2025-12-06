"""
DXF Thumbnail Generator
=======================
Generowanie miniatur z plików DXF przy użyciu ezdxf + matplotlib.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple
import io

logger = logging.getLogger(__name__)

# Cache miniatur
_thumbnail_cache: dict = {}

# Sprawdź dostępność bibliotek
try:
    import ezdxf
    from ezdxf.addons.drawing import RenderContext, Frontend
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    HAS_EZDXF_DRAWING = True
except ImportError:
    HAS_EZDXF_DRAWING = False
    logger.warning("ezdxf.addons.drawing not available. Install: pip install ezdxf matplotlib")

try:
    import matplotlib
    matplotlib.use('Agg')  # Backend bez GUI
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    logger.warning("matplotlib not available. Install: pip install matplotlib")

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    logger.warning("PIL not available. Install: pip install pillow")


def can_generate_thumbnails() -> bool:
    """Sprawdź czy generowanie miniatur jest dostępne"""
    return HAS_EZDXF_DRAWING and HAS_MATPLOTLIB and HAS_PIL


def get_dxf_thumbnail(
    dxf_path: str,
    img_size: Tuple[int, int] = (150, 150),
    bg_color: str = '#1a1a1a',
    line_color: str = '#ffffff',
    use_cache: bool = True
) -> Optional['Image.Image']:
    """
    Generuje miniaturę z pliku DXF.
    
    Args:
        dxf_path: Ścieżka do pliku DXF
        img_size: Rozmiar miniatury (width, height)
        bg_color: Kolor tła
        line_color: Kolor linii
        use_cache: Czy używać cache
        
    Returns:
        PIL.Image lub None jeśli błąd
    """
    if not can_generate_thumbnails():
        logger.warning("Thumbnail generation not available")
        return None
    
    # Sprawdź cache
    cache_key = f"{dxf_path}_{img_size}_{bg_color}_{line_color}"
    if use_cache and cache_key in _thumbnail_cache:
        return _thumbnail_cache[cache_key]
    
    try:
        # 1. Wczytaj DXF
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
        
        # Sprawdź czy są jakieś encje
        entities = list(msp)
        if not entities:
            logger.warning(f"No entities in DXF: {dxf_path}")
            return _create_placeholder(img_size, "Empty DXF")
        
        # 2. Przygotuj kontekst renderowania
        ctx = RenderContext(doc)
        
        # 3. Skonfiguruj Matplotlib
        fig = plt.figure(figsize=(img_size[0]/100, img_size[1]/100), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()
        ax.set_aspect('equal')
        ax.set_facecolor(bg_color)
        fig.patch.set_facecolor(bg_color)
        
        # 4. Backend Matplotlib
        out = MatplotlibBackend(ax)
        
        # 5. Rysowanie
        Frontend(ctx, out).draw_layout(msp, finalize=True)
        
        # 6. Zapis do bufora
        img_buffer = io.BytesIO()
        fig.savefig(
            img_buffer, 
            format='png', 
            dpi=100, 
            bbox_inches='tight', 
            pad_inches=0.05,
            facecolor=bg_color,
            edgecolor='none'
        )
        plt.close(fig)
        
        img_buffer.seek(0)
        
        # 7. Konwersja do PIL i skalowanie
        image = Image.open(img_buffer)
        image.thumbnail(img_size, Image.Resampling.LANCZOS)
        
        # Konwertuj do RGBA dla przezroczystości
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        # Cache
        if use_cache:
            _thumbnail_cache[cache_key] = image
        
        logger.debug(f"Generated thumbnail for: {dxf_path}")
        return image
        
    except Exception as e:
        logger.error(f"Error generating thumbnail for {dxf_path}: {e}")
        return _create_placeholder(img_size, "Error")


def _create_placeholder(size: Tuple[int, int], text: str = "?") -> Optional['Image.Image']:
    """Tworzy placeholder gdy nie można wygenerować miniatury"""
    if not HAS_PIL:
        return None
    
    try:
        from PIL import ImageDraw, ImageFont
        
        # Szary placeholder
        img = Image.new('RGBA', size, (40, 40, 40, 255))
        draw = ImageDraw.Draw(img)
        
        # Tekst na środku
        try:
            font = ImageFont.truetype("arial.ttf", 12)
        except:
            font = ImageFont.load_default()
        
        # Oblicz pozycję tekstu
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (size[0] - text_width) // 2
        y = (size[1] - text_height) // 2
        
        draw.text((x, y), text, fill=(128, 128, 128, 255), font=font)
        
        return img
    except:
        return None


def clear_thumbnail_cache():
    """Wyczyść cache miniatur"""
    global _thumbnail_cache
    _thumbnail_cache.clear()
    logger.debug("Thumbnail cache cleared")


def get_cache_size() -> int:
    """Zwróć liczbę miniatur w cache"""
    return len(_thumbnail_cache)


# =============================================================================
# Alternatywna metoda - prostsza, bez ezdxf.addons.drawing
# =============================================================================

def get_dxf_thumbnail_simple(
    dxf_path: str,
    img_size: Tuple[int, int] = (150, 150),
    bg_color: str = '#1a1a1a',
    line_color: str = '#8b5cf6'
) -> Optional['Image.Image']:
    """
    Prostsza metoda generowania miniatury - rysuje tylko kontury.
    Nie wymaga ezdxf.addons.drawing.
    
    Args:
        dxf_path: Ścieżka do pliku DXF
        img_size: Rozmiar miniatury
        bg_color: Kolor tła (hex)
        line_color: Kolor linii (hex)
    """
    if not HAS_PIL:
        return None
    
    try:
        import ezdxf
        from PIL import ImageDraw
        
        # Wczytaj DXF
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
        
        # Zbierz wszystkie punkty
        points = []
        
        for entity in msp:
            if entity.dxftype() == 'LWPOLYLINE':
                for x, y, *_ in entity.get_points('xy'):
                    points.append((x, y))
            elif entity.dxftype() == 'LINE':
                points.append((entity.dxf.start.x, entity.dxf.start.y))
                points.append((entity.dxf.end.x, entity.dxf.end.y))
            elif entity.dxftype() == 'CIRCLE':
                cx, cy = entity.dxf.center.x, entity.dxf.center.y
                r = entity.dxf.radius
                points.extend([(cx-r, cy), (cx+r, cy), (cx, cy-r), (cx, cy+r)])
            elif entity.dxftype() == 'ARC':
                cx, cy = entity.dxf.center.x, entity.dxf.center.y
                r = entity.dxf.radius
                points.extend([(cx-r, cy), (cx+r, cy), (cx, cy-r), (cx, cy+r)])
        
        if not points:
            return _create_placeholder(img_size, "Empty")
        
        # Oblicz bounding box
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        width = max_x - min_x
        height = max_y - min_y
        
        if width == 0 or height == 0:
            return _create_placeholder(img_size, "Invalid")
        
        # Skalowanie
        margin = 10
        scale_x = (img_size[0] - 2*margin) / width
        scale_y = (img_size[1] - 2*margin) / height
        scale = min(scale_x, scale_y)
        
        # Transformacja punktu
        def transform(x, y):
            tx = margin + (x - min_x) * scale
            ty = img_size[1] - margin - (y - min_y) * scale  # Odwróć Y
            return (tx, ty)
        
        # Konwersja koloru hex na RGB
        def hex_to_rgb(hex_color):
            hex_color = hex_color.lstrip('#')
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        
        # Utwórz obrazek
        bg_rgb = hex_to_rgb(bg_color)
        line_rgb = hex_to_rgb(line_color)
        
        img = Image.new('RGB', img_size, bg_rgb)
        draw = ImageDraw.Draw(img)
        
        # Rysuj encje
        for entity in msp:
            if entity.dxftype() == 'LWPOLYLINE':
                pts = [transform(x, y) for x, y, *_ in entity.get_points('xy')]
                if len(pts) >= 2:
                    if entity.closed:
                        draw.polygon(pts, outline=line_rgb)
                    else:
                        draw.line(pts, fill=line_rgb, width=1)
                        
            elif entity.dxftype() == 'LINE':
                p1 = transform(entity.dxf.start.x, entity.dxf.start.y)
                p2 = transform(entity.dxf.end.x, entity.dxf.end.y)
                draw.line([p1, p2], fill=line_rgb, width=1)
                
            elif entity.dxftype() == 'CIRCLE':
                cx, cy = entity.dxf.center.x, entity.dxf.center.y
                r = entity.dxf.radius
                p1 = transform(cx - r, cy - r)
                p2 = transform(cx + r, cy + r)
                # Popraw kolejność dla PIL (y może być odwrócone)
                x1, y1 = p1
                x2, y2 = p2
                draw.ellipse([x1, min(y1,y2), x2, max(y1,y2)], outline=line_rgb)
        
        return img
        
    except Exception as e:
        logger.error(f"Simple thumbnail error for {dxf_path}: {e}")
        return _create_placeholder(img_size, "Error")


# =============================================================================
# Funkcja wybierająca najlepszą dostępną metodę
# =============================================================================

def generate_thumbnail(
    dxf_path: str,
    img_size: Tuple[int, int] = (150, 150),
    bg_color: str = '#1a1a1a',
    line_color: str = '#8b5cf6'
) -> Optional['Image.Image']:
    """
    Generuje miniaturę używając najlepszej dostępnej metody.
    
    1. Jeśli dostępny ezdxf.addons.drawing - użyj pełnego renderingu
    2. W przeciwnym razie - użyj prostej metody
    """
    if can_generate_thumbnails():
        return get_dxf_thumbnail(dxf_path, img_size, bg_color, line_color)
    else:
        return get_dxf_thumbnail_simple(dxf_path, img_size, bg_color, line_color)
