"""
DXF Toolpath Extractor - Extract cutting paths and statistics from DXF files.

Extracts:
- Motion segments (lines, arcs, polylines)
- Cut length and rapid length
- Pierce count (number of contours)
- Entity counts
- Short segment ratio
- Occupied area (outer contour without holes)
"""

import math
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path

try:
    import ezdxf
    from ezdxf.entities import LWPolyline, Line, Arc, Circle, Spline, Polyline
    EZDXF_AVAILABLE = True
except ImportError:
    EZDXF_AVAILABLE = False

try:
    from shapely.geometry import Polygon, MultiPoint, LineString
    from shapely.ops import unary_union
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False

from ..motion.motion_planner import MotionSegment


@dataclass
class ToolpathStats:
    """Statistics extracted from DXF toolpath."""
    cut_length_mm: float = 0.0
    rapid_length_mm: float = 0.0
    engraving_length_mm: float = 0.0  # Długość grawerowania z warstw marking
    pierce_count: int = 0
    contour_count: int = 0
    entity_counts: Dict[str, int] = field(default_factory=dict)
    short_segment_ratio: float = 0.0
    occupied_area_mm2: float = 0.0
    net_area_mm2: float = 0.0
    bounding_box: Optional[Tuple[float, float, float, float]] = None  # (min_x, min_y, max_x, max_y)
    marking_layers: List[str] = field(default_factory=list)  # Znalezione warstwy graweru
    all_layers: List[str] = field(default_factory=list)  # Wszystkie warstwy w pliku


@dataclass
class ExtractedContour:
    """A single closed contour from DXF."""
    segments: List[MotionSegment]
    is_outer: bool = False
    area_mm2: float = 0.0
    perimeter_mm: float = 0.0


@dataclass
class DetailedToolpath:
    """Detailed toolpath with segments for accurate motion planning."""
    segments: List[MotionSegment]  # All segments from all contours
    contours: List[ExtractedContour]  # Contours grouped
    stats: ToolpathStats  # Summary statistics


# Layer keywords to ignore (drawings, dimensions, etc.)
DEFAULT_IGNORE_LAYERS = {
    'RAMKA', 'WYMIARY', 'DIM', 'TEXT', 'TEKST', 'OPIS',
    'DEFPOINTS', 'ASSEMBLY', 'HIDDEN', 'CENTER', 'CUTLINE',
    'GRID', 'TITLE', 'BLOCK', 'LOGO', 'INFO', 'FRAME',
    'BORDER', 'AM_', 'NOTES', 'KOTY', 'ZAKRES'
}

# Marking layer keywords (engraving, not cutting)
DEFAULT_MARKING_KEYWORDS = {
    'grawer', 'marking', 'opis', 'text', 'engrave', 'mark', 'sign'
}

# Short segment threshold
SHORT_SEGMENT_THRESHOLD_MM = 5.0


def is_layer_ignored(layer_name: str, ignore_layers: Set[str]) -> bool:
    """Check if layer should be ignored."""
    layer_upper = layer_name.upper()
    for ignore in ignore_layers:
        if ignore.upper() in layer_upper:
            return True
    return False


def is_marking_layer(layer_name: str, marking_keywords: Set[str]) -> bool:
    """Check if layer is for marking/engraving (not cutting through)."""
    layer_lower = layer_name.lower()
    for keyword in marking_keywords:
        if keyword.lower() in layer_lower:
            return True
    return False


def extract_line_segment(entity) -> Optional[MotionSegment]:
    """Extract motion segment from LINE entity."""
    start = entity.dxf.start
    end = entity.dxf.end

    dx = end.x - start.x
    dy = end.y - start.y
    length = math.sqrt(dx*dx + dy*dy)

    if length < 0.001:
        return None

    angle = math.degrees(math.atan2(dy, dx))

    return MotionSegment(
        length_mm=length,
        start_angle_deg=angle,
        end_angle_deg=angle,
        is_rapid=False
    )


def extract_arc_segments(entity, tolerance_mm: float = 0.2) -> List[MotionSegment]:
    """Extract motion segments from ARC entity (approximate with line segments)."""
    segments = []

    center = entity.dxf.center
    radius = entity.dxf.radius
    start_angle = math.radians(entity.dxf.start_angle)
    end_angle = math.radians(entity.dxf.end_angle)

    # Normalize angles
    while end_angle <= start_angle:
        end_angle += 2 * math.pi

    arc_length = radius * (end_angle - start_angle)

    # Calculate number of segments based on tolerance
    if radius > 0:
        # Chord error formula: e = r * (1 - cos(theta/2))
        # Solve for theta: theta = 2 * acos(1 - e/r)
        if tolerance_mm < radius:
            theta_max = 2 * math.acos(1 - tolerance_mm / radius)
        else:
            theta_max = math.pi / 8  # Max 22.5 degrees

        n_segments = max(1, int(math.ceil((end_angle - start_angle) / theta_max)))
    else:
        return segments

    delta_angle = (end_angle - start_angle) / n_segments

    for i in range(n_segments):
        a1 = start_angle + i * delta_angle
        a2 = start_angle + (i + 1) * delta_angle

        # Tangent direction at start and end
        tangent_start = math.degrees(a1 + math.pi/2)
        tangent_end = math.degrees(a2 + math.pi/2)

        seg_length = radius * delta_angle

        segments.append(MotionSegment(
            length_mm=seg_length,
            start_angle_deg=tangent_start,
            end_angle_deg=tangent_end,
            is_rapid=False
        ))

    return segments


def extract_circle_segments(entity, n_segments: int = 32) -> List[MotionSegment]:
    """Extract motion segments from CIRCLE entity."""
    segments = []
    radius = entity.dxf.radius

    if radius <= 0:
        return segments

    circumference = 2 * math.pi * radius
    seg_length = circumference / n_segments
    delta_angle = 2 * math.pi / n_segments

    for i in range(n_segments):
        a1 = i * delta_angle
        a2 = (i + 1) * delta_angle

        tangent_start = math.degrees(a1 + math.pi/2)
        tangent_end = math.degrees(a2 + math.pi/2)

        segments.append(MotionSegment(
            length_mm=seg_length,
            start_angle_deg=tangent_start,
            end_angle_deg=tangent_end,
            is_rapid=False
        ))

    return segments


def extract_lwpolyline_segments(entity, tolerance_mm: float = 0.2) -> List[MotionSegment]:
    """Extract motion segments from LWPOLYLINE entity."""
    segments = []

    points = list(entity.get_points('xyseb'))  # x, y, start_width, end_width, bulge

    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]

        bulge = p1[4] if len(p1) > 4 else 0

        if abs(bulge) < 0.001:
            # Straight segment
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            length = math.sqrt(dx*dx + dy*dy)

            if length > 0.001:
                angle = math.degrees(math.atan2(dy, dx))
                segments.append(MotionSegment(
                    length_mm=length,
                    start_angle_deg=angle,
                    end_angle_deg=angle,
                    is_rapid=False
                ))
        else:
            # Arc segment (bulge != 0)
            arc_segs = _bulge_to_segments(
                p1[0], p1[1], p2[0], p2[1], bulge, tolerance_mm
            )
            segments.extend(arc_segs)

    # Handle closed polyline
    if entity.closed and len(points) >= 2:
        p1 = points[-1]
        p2 = points[0]
        bulge = p1[4] if len(p1) > 4 else 0

        if abs(bulge) < 0.001:
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            length = math.sqrt(dx*dx + dy*dy)

            if length > 0.001:
                angle = math.degrees(math.atan2(dy, dx))
                segments.append(MotionSegment(
                    length_mm=length,
                    start_angle_deg=angle,
                    end_angle_deg=angle,
                    is_rapid=False
                ))
        else:
            arc_segs = _bulge_to_segments(
                p1[0], p1[1], p2[0], p2[1], bulge, tolerance_mm
            )
            segments.extend(arc_segs)

    return segments


def _bulge_to_segments(x1: float, y1: float, x2: float, y2: float,
                       bulge: float, tolerance_mm: float) -> List[MotionSegment]:
    """Convert bulge arc to line segments."""
    segments = []

    # Bulge = tan(theta/4) where theta is the arc angle
    theta = 4 * math.atan(abs(bulge))
    chord_length = math.sqrt((x2-x1)**2 + (y2-y1)**2)

    if chord_length < 0.001:
        return segments

    # Radius = chord / (2 * sin(theta/2))
    sin_half = math.sin(theta / 2)
    if sin_half < 0.001:
        # Nearly straight
        angle = math.degrees(math.atan2(y2-y1, x2-x1))
        return [MotionSegment(
            length_mm=chord_length,
            start_angle_deg=angle,
            end_angle_deg=angle,
            is_rapid=False
        )]

    radius = chord_length / (2 * sin_half)
    arc_length = radius * theta

    # Number of segments
    if tolerance_mm < radius:
        theta_max = 2 * math.acos(1 - tolerance_mm / radius)
    else:
        theta_max = math.pi / 8

    n_segments = max(1, int(math.ceil(theta / theta_max)))
    seg_length = arc_length / n_segments

    # Calculate center
    chord_angle = math.atan2(y2-y1, x2-x1)
    d = chord_length / 2
    h = radius * math.cos(theta/2)  # Distance from chord midpoint to center

    mid_x = (x1 + x2) / 2
    mid_y = (y1 + y2) / 2

    # Perpendicular direction (depends on bulge sign)
    perp_angle = chord_angle + (math.pi/2 if bulge > 0 else -math.pi/2)
    cx = mid_x + h * math.cos(perp_angle)
    cy = mid_y + h * math.sin(perp_angle)

    # Start and end angles from center
    start_angle = math.atan2(y1 - cy, x1 - cx)
    end_angle = math.atan2(y2 - cy, x2 - cx)

    # Direction
    if bulge > 0:  # CCW
        while end_angle <= start_angle:
            end_angle += 2 * math.pi
    else:  # CW
        while end_angle >= start_angle:
            end_angle -= 2 * math.pi

    delta = (end_angle - start_angle) / n_segments

    for i in range(n_segments):
        a1 = start_angle + i * delta
        a2 = start_angle + (i + 1) * delta

        # Tangent direction
        if bulge > 0:
            tangent_start = math.degrees(a1 + math.pi/2)
            tangent_end = math.degrees(a2 + math.pi/2)
        else:
            tangent_start = math.degrees(a1 - math.pi/2)
            tangent_end = math.degrees(a2 - math.pi/2)

        segments.append(MotionSegment(
            length_mm=seg_length,
            start_angle_deg=tangent_start,
            end_angle_deg=tangent_end,
            is_rapid=False
        ))

    return segments


def extract_spline_segments(entity, tolerance_mm: float = 0.2) -> List[MotionSegment]:
    """Extract motion segments from SPLINE entity (approximate with points)."""
    segments = []

    try:
        # Get flattened points
        points = list(entity.flattening(tolerance_mm))

        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i + 1]

            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            length = math.sqrt(dx*dx + dy*dy)

            if length > 0.001:
                angle = math.degrees(math.atan2(dy, dx))
                segments.append(MotionSegment(
                    length_mm=length,
                    start_angle_deg=angle,
                    end_angle_deg=angle,
                    is_rapid=False
                ))
    except Exception:
        # Fallback: use control points
        try:
            points = list(entity.control_points)
            for i in range(len(points) - 1):
                p1 = points[i]
                p2 = points[i + 1]

                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                length = math.sqrt(dx*dx + dy*dy)

                if length > 0.001:
                    angle = math.degrees(math.atan2(dy, dx))
                    segments.append(MotionSegment(
                        length_mm=length,
                        start_angle_deg=angle,
                        end_angle_deg=angle,
                        is_rapid=False
                    ))
        except Exception:
            pass

    return segments


def extract_toolpath_stats(dxf_path: str,
                           ignore_layers: Optional[Set[str]] = None,
                           marking_keywords: Optional[Set[str]] = None,
                           tolerance_mm: float = 0.2) -> ToolpathStats:
    """
    Extract toolpath statistics from a DXF file.

    Args:
        dxf_path: Path to DXF file
        ignore_layers: Layer names to skip (default: standard non-cutting layers)
        marking_keywords: Keywords for marking/engraving layers
        tolerance_mm: Tolerance for arc/spline approximation

    Returns:
        ToolpathStats with extracted statistics
    """
    if not EZDXF_AVAILABLE:
        raise ImportError("ezdxf library is required for DXF extraction")

    if ignore_layers is None:
        ignore_layers = DEFAULT_IGNORE_LAYERS
    if marking_keywords is None:
        marking_keywords = DEFAULT_MARKING_KEYWORDS

    stats = ToolpathStats()
    all_segments: List[MotionSegment] = []
    all_points: List[Tuple[float, float]] = []

    try:
        doc = ezdxf.readfile(dxf_path)
    except Exception as e:
        raise ValueError(f"Cannot read DXF file: {e}")

    msp = doc.modelspace()

    # Entity type counters
    entity_counts = {'LINE': 0, 'ARC': 0, 'CIRCLE': 0, 'LWPOLYLINE': 0, 'SPLINE': 0}

    # Track contours (closed shapes = 1 pierce each)
    contour_endpoints: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []

    # Track all layers and marking layers
    all_layers_set = set()
    marking_layers_set = set()
    engraving_length = 0.0

    for entity in msp:
        layer = entity.dxf.layer
        all_layers_set.add(layer)

        # Skip ignored layers
        if is_layer_ignored(layer, ignore_layers):
            continue

        # Handle marking layers - track engraving length
        is_marking = is_marking_layer(layer, marking_keywords)
        if is_marking:
            marking_layers_set.add(layer)
            # Calculate engraving length from this entity
            etype = entity.dxftype()
            if etype == 'LINE':
                start = entity.dxf.start
                end = entity.dxf.end
                dx = end.x - start.x
                dy = end.y - start.y
                engraving_length += math.sqrt(dx*dx + dy*dy)
            elif etype == 'ARC':
                radius = entity.dxf.radius
                start_a = math.radians(entity.dxf.start_angle)
                end_a = math.radians(entity.dxf.end_angle)
                while end_a <= start_a:
                    end_a += 2 * math.pi
                engraving_length += radius * (end_a - start_a)
            elif etype == 'CIRCLE':
                engraving_length += 2 * math.pi * entity.dxf.radius
            elif etype == 'LWPOLYLINE':
                points = list(entity.get_points('xyb'))
                for i in range(len(points) - 1):
                    p1, p2 = points[i], points[i + 1]
                    dx = p2[0] - p1[0]
                    dy = p2[1] - p1[1]
                    engraving_length += math.sqrt(dx*dx + dy*dy)
                if entity.closed and len(points) >= 2:
                    p1, p2 = points[-1], points[0]
                    dx = p2[0] - p1[0]
                    dy = p2[1] - p1[1]
                    engraving_length += math.sqrt(dx*dx + dy*dy)
            continue  # Skip adding to cutting stats

        etype = entity.dxftype()
        segments = []

        if etype == 'LINE':
            entity_counts['LINE'] += 1
            seg = extract_line_segment(entity)
            if seg:
                segments = [seg]
                p1 = (entity.dxf.start.x, entity.dxf.start.y)
                p2 = (entity.dxf.end.x, entity.dxf.end.y)
                all_points.extend([p1, p2])
                contour_endpoints.append((p1, p2))

        elif etype == 'ARC':
            entity_counts['ARC'] += 1
            segments = extract_arc_segments(entity, tolerance_mm)
            # Get arc endpoints
            center = entity.dxf.center
            radius = entity.dxf.radius
            start_a = math.radians(entity.dxf.start_angle)
            end_a = math.radians(entity.dxf.end_angle)
            p1 = (center.x + radius * math.cos(start_a),
                  center.y + radius * math.sin(start_a))
            p2 = (center.x + radius * math.cos(end_a),
                  center.y + radius * math.sin(end_a))
            all_points.extend([p1, p2])
            contour_endpoints.append((p1, p2))

        elif etype == 'CIRCLE':
            entity_counts['CIRCLE'] += 1
            segments = extract_circle_segments(entity)
            # Circle is always closed - 1 contour
            center = entity.dxf.center
            radius = entity.dxf.radius
            # Add points around circle for bounding box
            for i in range(8):
                a = i * math.pi / 4
                all_points.append((center.x + radius * math.cos(a),
                                   center.y + radius * math.sin(a)))
            stats.contour_count += 1

        elif etype == 'LWPOLYLINE':
            entity_counts['LWPOLYLINE'] += 1
            segments = extract_lwpolyline_segments(entity, tolerance_mm)
            points = list(entity.get_points('xy'))
            all_points.extend([(p[0], p[1]) for p in points])
            if entity.closed:
                stats.contour_count += 1
            else:
                if len(points) >= 2:
                    contour_endpoints.append(
                        ((points[0][0], points[0][1]),
                         (points[-1][0], points[-1][1]))
                    )

        elif etype == 'SPLINE':
            entity_counts['SPLINE'] += 1
            segments = extract_spline_segments(entity, tolerance_mm)
            try:
                points = list(entity.flattening(tolerance_mm))
                all_points.extend([(p[0], p[1]) for p in points])
            except Exception:
                pass

        all_segments.extend(segments)

    # Count contours from open paths
    stats.contour_count += _count_open_contours(contour_endpoints)

    # Pierce count = contour count (1 pierce per contour start)
    stats.pierce_count = stats.contour_count

    # Calculate total lengths
    total_length = sum(s.length_mm for s in all_segments)
    short_length = sum(s.length_mm for s in all_segments
                       if s.length_mm < SHORT_SEGMENT_THRESHOLD_MM)

    stats.cut_length_mm = total_length
    stats.entity_counts = entity_counts
    stats.short_segment_ratio = short_length / total_length if total_length > 0 else 0.0

    # Calculate bounding box and area
    if all_points:
        xs = [p[0] for p in all_points]
        ys = [p[1] for p in all_points]
        stats.bounding_box = (min(xs), min(ys), max(xs), max(ys))

        # Calculate occupied area using convex hull
        if SHAPELY_AVAILABLE and len(all_points) >= 3:
            try:
                hull = MultiPoint(all_points).convex_hull
                if hasattr(hull, 'area'):
                    stats.occupied_area_mm2 = hull.area
            except Exception:
                # Fallback to bounding box
                width = max(xs) - min(xs)
                height = max(ys) - min(ys)
                stats.occupied_area_mm2 = width * height
        else:
            width = max(xs) - min(xs)
            height = max(ys) - min(ys)
            stats.occupied_area_mm2 = width * height

    # Add engraving stats
    stats.engraving_length_mm = engraving_length
    stats.marking_layers = sorted(list(marking_layers_set))
    stats.all_layers = sorted(list(all_layers_set))

    return stats


def _count_open_contours(endpoints: List[Tuple[Tuple[float, float], Tuple[float, float]]],
                         tolerance: float = 0.1) -> int:
    """
    Count number of contours formed by chaining open paths.

    Uses a simple endpoint matching algorithm.
    """
    if not endpoints:
        return 0

    # Track which endpoints are used
    used = [False] * len(endpoints)
    contour_count = 0

    for i, (start, end) in enumerate(endpoints):
        if used[i]:
            continue

        # Start a new contour
        contour_count += 1
        used[i] = True
        current_end = end

        # Try to extend the contour
        changed = True
        while changed:
            changed = False
            for j, (s, e) in enumerate(endpoints):
                if used[j]:
                    continue

                # Check if this segment connects
                if _points_close(current_end, s, tolerance):
                    used[j] = True
                    current_end = e
                    changed = True
                elif _points_close(current_end, e, tolerance):
                    used[j] = True
                    current_end = s
                    changed = True

    return contour_count


def _points_close(p1: Tuple[float, float], p2: Tuple[float, float],
                  tolerance: float) -> bool:
    """Check if two points are within tolerance."""
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    return dx*dx + dy*dy < tolerance * tolerance


def extract_motion_segments(dxf_path: str,
                            ignore_layers: Optional[Set[str]] = None,
                            tolerance_mm: float = 0.2) -> List[MotionSegment]:
    """
    Extract all motion segments from a DXF file.

    For use with detailed motion planning.
    Each DXF entity (CIRCLE, LWPOLYLINE, etc.) is assigned a unique contour_id
    to enable proper start/stop velocity planning.

    Args:
        dxf_path: Path to DXF file
        ignore_layers: Layer names to skip
        tolerance_mm: Tolerance for arc/spline approximation

    Returns:
        List of MotionSegment objects with contour_id assigned
    """
    if not EZDXF_AVAILABLE:
        raise ImportError("ezdxf library is required")

    if ignore_layers is None:
        ignore_layers = DEFAULT_IGNORE_LAYERS

    segments: List[MotionSegment] = []
    contour_id = 0  # Counter for unique contour IDs

    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    for entity in msp:
        if is_layer_ignored(entity.dxf.layer, ignore_layers):
            continue

        etype = entity.dxftype()
        entity_segments = []

        if etype == 'LINE':
            seg = extract_line_segment(entity)
            if seg:
                entity_segments = [seg]
        elif etype == 'ARC':
            entity_segments = extract_arc_segments(entity, tolerance_mm)
        elif etype == 'CIRCLE':
            entity_segments = extract_circle_segments(entity)
        elif etype == 'LWPOLYLINE':
            entity_segments = extract_lwpolyline_segments(entity, tolerance_mm)
        elif etype == 'SPLINE':
            entity_segments = extract_spline_segments(entity, tolerance_mm)

        # Assign contour_id to all segments from this entity
        if entity_segments:
            for seg in entity_segments:
                seg.contour_id = contour_id
            segments.extend(entity_segments)
            contour_id += 1  # Next entity gets new contour_id

    return segments


@dataclass
class EngravingInfo:
    """Information about engraving/marking in a DXF file."""
    engraving_length_mm: float = 0.0
    marking_layers: List[str] = field(default_factory=list)
    all_layers: List[str] = field(default_factory=list)
    has_engraving: bool = False


def extract_engraving_info(dxf_path: str,
                           marking_keywords: Optional[Set[str]] = None) -> EngravingInfo:
    """
    Extract engraving/marking information from a DXF file.

    This is a lightweight function that only extracts engraving data,
    useful for quick analysis after loading DXF files.

    Args:
        dxf_path: Path to DXF file
        marking_keywords: Keywords to identify marking layers (default: standard keywords)

    Returns:
        EngravingInfo with engraving length and layer information
    """
    if not EZDXF_AVAILABLE:
        return EngravingInfo()

    if marking_keywords is None:
        marking_keywords = DEFAULT_MARKING_KEYWORDS

    info = EngravingInfo()
    all_layers = set()
    marking_layers = set()
    engraving_length = 0.0

    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()

        for entity in msp:
            layer = entity.dxf.layer
            all_layers.add(layer)

            if is_marking_layer(layer, marking_keywords):
                marking_layers.add(layer)
                etype = entity.dxftype()

                # Calculate length
                if etype == 'LINE':
                    start = entity.dxf.start
                    end = entity.dxf.end
                    dx = end.x - start.x
                    dy = end.y - start.y
                    engraving_length += math.sqrt(dx*dx + dy*dy)

                elif etype == 'ARC':
                    radius = entity.dxf.radius
                    start_a = math.radians(entity.dxf.start_angle)
                    end_a = math.radians(entity.dxf.end_angle)
                    while end_a <= start_a:
                        end_a += 2 * math.pi
                    engraving_length += radius * (end_a - start_a)

                elif etype == 'CIRCLE':
                    engraving_length += 2 * math.pi * entity.dxf.radius

                elif etype == 'LWPOLYLINE':
                    points = list(entity.get_points('xy'))
                    for i in range(len(points) - 1):
                        p1, p2 = points[i], points[i + 1]
                        dx = p2[0] - p1[0]
                        dy = p2[1] - p1[1]
                        engraving_length += math.sqrt(dx*dx + dy*dy)
                    if entity.closed and len(points) >= 2:
                        p1, p2 = points[-1], points[0]
                        dx = p2[0] - p1[0]
                        dy = p2[1] - p1[1]
                        engraving_length += math.sqrt(dx*dx + dy*dy)

        info.engraving_length_mm = engraving_length
        info.marking_layers = sorted(list(marking_layers))
        info.all_layers = sorted(list(all_layers))
        info.has_engraving = engraving_length > 0

    except Exception as e:
        logger.warning(f"Could not extract engraving info from {dxf_path}: {e}")

    return info
