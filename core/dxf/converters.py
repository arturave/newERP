"""
DXF Entity Converters - Konwersja entities DXF na punkty
========================================================
Obsługuje: LINE, ARC, CIRCLE, LWPOLYLINE, POLYLINE, SPLINE, ELLIPSE
"""

import math
import logging
from typing import List, Tuple, Optional, Dict, Any

from .entities import DXFEntity, EntityType

logger = logging.getLogger(__name__)

# Importy ezdxf z lazy loading
try:
    import ezdxf
    from ezdxf import path as ezdxf_path
    from ezdxf.math import bulge_to_arc
    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False
    logger.warning("ezdxf not installed - DXF support disabled")


def arc_to_points(
    center_x: float, center_y: float,
    radius: float,
    start_angle_deg: float, end_angle_deg: float,
    resolution: int = 8
) -> Tuple[List[Tuple[float, float]], float]:
    """
    Konwertuj łuk na listę punktów.

    Args:
        center_x, center_y: Środek łuku
        radius: Promień
        start_angle_deg, end_angle_deg: Kąty w stopniach
        resolution: Punkty na 90 stopni

    Returns:
        (points, arc_length) - lista punktów i długość łuku
    """
    points = []

    start_rad = math.radians(start_angle_deg)
    end_rad = math.radians(end_angle_deg)

    # Obsłuż przypadek gdy end < start (łuk przechodzi przez 0°)
    if end_angle_deg < start_angle_deg:
        end_rad += 2 * math.pi

    arc_angle = abs(end_rad - start_rad)
    num_points = max(3, int(arc_angle / (math.pi / 2) * resolution) + 1)

    for i in range(num_points + 1):
        t = i / num_points
        angle = start_rad + t * (end_rad - start_rad)
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        points.append((x, y))

    arc_length = radius * arc_angle
    return points, arc_length


def circle_to_points(
    center_x: float, center_y: float,
    radius: float,
    resolution: int = 32
) -> Tuple[List[Tuple[float, float]], float]:
    """
    Konwertuj okrąg na listę punktów.

    Args:
        center_x, center_y: Środek okręgu
        radius: Promień
        resolution: Liczba punktów

    Returns:
        (points, circumference) - lista punktów i obwód
    """
    points = []
    for i in range(resolution):
        angle = 2 * math.pi * i / resolution
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        points.append((x, y))

    # Zamknij okrąg
    points.append(points[0])

    circumference = 2 * math.pi * radius
    return points, circumference


def bulge_arc_to_points(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    bulge: float,
    resolution: int = 8
) -> Tuple[List[Tuple[float, float]], float]:
    """
    Konwertuj łuk zdefiniowany przez bulge (z LWPOLYLINE) na punkty.

    Args:
        p1: Punkt początkowy
        p2: Punkt końcowy
        bulge: Wartość bulge (tan(angle/4))
        resolution: Punkty na 90 stopni

    Returns:
        (points, arc_length) - lista punktów i długość łuku
    """
    if abs(bulge) < 1e-10:
        # To linia prosta
        return [p1, p2], math.dist(p1, p2)

    if not HAS_EZDXF:
        # Fallback bez ezdxf - prosta linia
        return [p1, p2], math.dist(p1, p2)

    try:
        center, start_angle, end_angle, radius = bulge_to_arc(p1, p2, bulge)

        # Konwertuj radiany na stopnie dla arc_to_points
        start_deg = math.degrees(start_angle)
        end_deg = math.degrees(end_angle)

        # Obsłuż znak bulge (kierunek łuku)
        if bulge < 0:
            start_deg, end_deg = end_deg, start_deg

        points, length = arc_to_points(
            center[0], center[1], radius,
            start_deg, end_deg, resolution
        )

        return points, length
    except Exception as e:
        logger.debug(f"Bulge conversion error: {e}")
        return [p1, p2], math.dist(p1, p2)


def convert_line(entity) -> DXFEntity:
    """Konwertuj LINE entity"""
    start = (entity.dxf.start.x, entity.dxf.start.y)
    end = (entity.dxf.end.x, entity.dxf.end.y)

    length = math.dist(start, end)

    return DXFEntity(
        entity_type=EntityType.LINE,
        layer=entity.dxf.layer,
        color=entity.dxf.color if hasattr(entity.dxf, 'color') else 256,
        points=[start, end],
        is_closed=False,
        length_mm=length,
        raw_data={
            'start': start,
            'end': end
        }
    )


def convert_arc(entity, resolution: int = 8) -> DXFEntity:
    """Konwertuj ARC entity"""
    cx, cy = entity.dxf.center.x, entity.dxf.center.y
    radius = entity.dxf.radius
    start_angle = entity.dxf.start_angle
    end_angle = entity.dxf.end_angle

    points, length = arc_to_points(cx, cy, radius, start_angle, end_angle, resolution)

    return DXFEntity(
        entity_type=EntityType.ARC,
        layer=entity.dxf.layer,
        color=entity.dxf.color if hasattr(entity.dxf, 'color') else 256,
        points=points,
        is_closed=False,
        length_mm=length,
        raw_data={
            'center': (cx, cy),
            'radius': radius,
            'start_angle': start_angle,
            'end_angle': end_angle
        }
    )


def convert_circle(entity, resolution: int = 32) -> DXFEntity:
    """Konwertuj CIRCLE entity"""
    cx, cy = entity.dxf.center.x, entity.dxf.center.y
    radius = entity.dxf.radius

    points, length = circle_to_points(cx, cy, radius, resolution)

    return DXFEntity(
        entity_type=EntityType.CIRCLE,
        layer=entity.dxf.layer,
        color=entity.dxf.color if hasattr(entity.dxf, 'color') else 256,
        points=points,
        is_closed=True,
        length_mm=length,
        raw_data={
            'center': (cx, cy),
            'radius': radius
        }
    )


def convert_lwpolyline(entity, arc_resolution: int = 8) -> DXFEntity:
    """Konwertuj LWPOLYLINE entity (z obsługą bulge)"""
    points = []
    total_length = 0.0

    try:
        pts_bulge = list(entity.get_points('xyb'))
        n = len(pts_bulge)

        for i in range(n):
            x, y = pts_bulge[i][0], pts_bulge[i][1]
            bulge = pts_bulge[i][2] if len(pts_bulge[i]) > 2 else 0

            if i == 0:
                points.append((x, y))

            if i < n - 1 or entity.closed:
                next_idx = (i + 1) % n
                next_pt = (pts_bulge[next_idx][0], pts_bulge[next_idx][1])

                if abs(bulge) > 1e-10:
                    # Łuk z bulge
                    arc_points, arc_len = bulge_arc_to_points(
                        (x, y), next_pt, bulge, arc_resolution
                    )
                    # Dodaj bez pierwszego punktu (już jest)
                    points.extend(arc_points[1:])
                    total_length += arc_len
                else:
                    # Linia prosta
                    if i < n - 1:
                        points.append(next_pt)
                    total_length += math.dist((x, y), next_pt)

        # Zamknij jeśli potrzeba
        if entity.closed and points and points[-1] != points[0]:
            points.append(points[0])

    except Exception as e:
        logger.debug(f"LWPOLYLINE conversion error: {e}")
        # Fallback - tylko punkty xy
        try:
            points = [(p[0], p[1]) for p in entity.get_points('xy')]
            if entity.closed and points:
                points.append(points[0])
            # Oblicz długość
            for i in range(len(points) - 1):
                total_length += math.dist(points[i], points[i+1])
        except:
            pass

    return DXFEntity(
        entity_type=EntityType.LWPOLYLINE,
        layer=entity.dxf.layer,
        color=entity.dxf.color if hasattr(entity.dxf, 'color') else 256,
        points=points,
        is_closed=entity.closed,
        length_mm=total_length,
        raw_data={
            'closed': entity.closed
        }
    )


def convert_polyline(entity, arc_resolution: int = 8) -> DXFEntity:
    """Konwertuj POLYLINE (stary format 3D)"""
    points = []
    total_length = 0.0

    try:
        vertices = list(entity.vertices)

        for i, v in enumerate(vertices):
            x, y = v.dxf.location.x, v.dxf.location.y
            bulge = v.dxf.bulge if hasattr(v.dxf, 'bulge') else 0

            if i == 0:
                points.append((x, y))

            if i < len(vertices) - 1 or entity.is_closed:
                next_idx = (i + 1) % len(vertices)
                next_v = vertices[next_idx]
                next_pt = (next_v.dxf.location.x, next_v.dxf.location.y)

                if abs(bulge) > 1e-10:
                    arc_points, arc_len = bulge_arc_to_points(
                        (x, y), next_pt, bulge, arc_resolution
                    )
                    points.extend(arc_points[1:])
                    total_length += arc_len
                else:
                    if i < len(vertices) - 1:
                        points.append(next_pt)
                    total_length += math.dist((x, y), next_pt)

        if entity.is_closed and points and points[-1] != points[0]:
            points.append(points[0])

    except Exception as e:
        logger.debug(f"POLYLINE conversion error: {e}")

    return DXFEntity(
        entity_type=EntityType.POLYLINE,
        layer=entity.dxf.layer,
        color=entity.dxf.color if hasattr(entity.dxf, 'color') else 256,
        points=points,
        is_closed=entity.is_closed if hasattr(entity, 'is_closed') else False,
        length_mm=total_length,
        raw_data={}
    )


def convert_spline(entity, tolerance_mm: float = 0.2) -> DXFEntity:
    """Konwertuj SPLINE entity (aproksymacja punktami)"""
    points = []
    total_length = 0.0

    try:
        # Użyj flattening do aproksymacji
        flat_points = list(entity.flattening(tolerance_mm))
        points = [(p[0], p[1]) for p in flat_points]

        # Oblicz długość
        for i in range(len(points) - 1):
            total_length += math.dist(points[i], points[i+1])

    except Exception:
        # Fallback - control points
        try:
            ctrl_points = list(entity.control_points)
            points = [(p[0], p[1]) for p in ctrl_points]

            for i in range(len(points) - 1):
                total_length += math.dist(points[i], points[i+1])
        except Exception as e:
            logger.debug(f"SPLINE conversion error: {e}")

    is_closed = entity.closed if hasattr(entity, 'closed') else False

    return DXFEntity(
        entity_type=EntityType.SPLINE,
        layer=entity.dxf.layer,
        color=entity.dxf.color if hasattr(entity.dxf, 'color') else 256,
        points=points,
        is_closed=is_closed,
        length_mm=total_length,
        raw_data={}
    )


def convert_ellipse(entity, resolution: int = 32) -> DXFEntity:
    """Konwertuj ELLIPSE entity"""
    points = []
    total_length = 0.0

    try:
        # Użyj ezdxf.path do konwersji
        p = ezdxf_path.make_path(entity)

        # Flatten do punktów
        flat_points = list(p.flattening(0.2))
        points = [(pt[0], pt[1]) for pt in flat_points]

        # Długość z path
        total_length = p.length()

    except Exception as e:
        logger.debug(f"ELLIPSE conversion error: {e}")
        # Fallback - aproksymacja jako okrąg
        try:
            center = entity.dxf.center
            major_axis = entity.dxf.major_axis
            ratio = entity.dxf.ratio

            # Przybliżony promień
            r = math.sqrt(major_axis[0]**2 + major_axis[1]**2)
            points, total_length = circle_to_points(
                center[0], center[1], r, resolution
            )
        except:
            pass

    is_closed = True  # Elipsy są zawsze zamknięte

    return DXFEntity(
        entity_type=EntityType.ELLIPSE,
        layer=entity.dxf.layer,
        color=entity.dxf.color if hasattr(entity.dxf, 'color') else 256,
        points=points,
        is_closed=is_closed,
        length_mm=total_length,
        raw_data={}
    )


def convert_entity(entity, arc_resolution: int = 8, spline_tolerance: float = 0.2) -> Optional[DXFEntity]:
    """
    Uniwersalny konwerter entity DXF.

    Args:
        entity: Entity ezdxf
        arc_resolution: Rozdzielczość łuków (punkty na 90°)
        spline_tolerance: Tolerancja aproksymacji spline (mm)

    Returns:
        DXFEntity lub None jeśli nieobsługiwany typ
    """
    if not HAS_EZDXF:
        return None

    etype = entity.dxftype()

    converters = {
        'LINE': lambda e: convert_line(e),
        'ARC': lambda e: convert_arc(e, arc_resolution),
        'CIRCLE': lambda e: convert_circle(e),
        'LWPOLYLINE': lambda e: convert_lwpolyline(e, arc_resolution),
        'POLYLINE': lambda e: convert_polyline(e, arc_resolution),
        'SPLINE': lambda e: convert_spline(e, spline_tolerance),
        'ELLIPSE': lambda e: convert_ellipse(e),
    }

    converter = converters.get(etype)
    if converter:
        try:
            return converter(entity)
        except Exception as e:
            logger.warning(f"Error converting {etype}: {e}")
            return None

    # Nieobsługiwane typy
    if etype not in ('POINT', 'TEXT', 'MTEXT', 'DIMENSION', 'INSERT', 'HATCH', 'SOLID'):
        logger.debug(f"Unsupported entity type: {etype}")

    return None


# Eksporty
__all__ = [
    'arc_to_points',
    'circle_to_points',
    'bulge_arc_to_points',
    'convert_line',
    'convert_arc',
    'convert_circle',
    'convert_lwpolyline',
    'convert_polyline',
    'convert_spline',
    'convert_ellipse',
    'convert_entity',
    'HAS_EZDXF',
]
