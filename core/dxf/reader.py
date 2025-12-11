"""
Unified DXF Reader - Centralny odczyt plików DXF
================================================
Konsoliduje logikę z wielu plików w jeden spójny interfejs.
"""

import os
import re
import logging
from typing import Optional, Dict, List, Tuple, Any
from pathlib import Path

from .entities import DXFPart, DXFContour, DXFEntity, LayerInfo, EntityType
from .converters import convert_entity, HAS_EZDXF
from .contour_builder import ContourBuilder, build_contours_from_entities
from .layer_filters import (
    is_ignored_layer, is_outer_layer, is_inner_layer,
    is_feature_layer, get_layer_priority, classify_layer
)

logger = logging.getLogger(__name__)

if HAS_EZDXF:
    import ezdxf


class UnifiedDXFReader:
    """
    Centralny reader plików DXF.

    Obsługuje:
    - LINE, ARC, CIRCLE, LWPOLYLINE, POLYLINE, SPLINE, ELLIPSE
    - Automatyczne łączenie entities w zamknięte kontury
    - Filtrowanie warstw (ignorowane, zewnętrzne, wewnętrzne)
    - Parsowanie metadanych z nazwy pliku
    """

    def __init__(
        self,
        arc_resolution: int = 8,
        spline_tolerance: float = 0.2,
        contour_tolerance: float = 1.0
    ):
        """
        Args:
            arc_resolution: Punkty na 90° dla łuków
            spline_tolerance: Tolerancja aproksymacji spline (mm)
            contour_tolerance: Tolerancja łączenia końców segmentów (mm)
        """
        self.arc_resolution = arc_resolution
        self.spline_tolerance = spline_tolerance
        self.contour_tolerance = contour_tolerance
        self._contour_builder = ContourBuilder(contour_tolerance)

    def read(self, filepath: str) -> Optional[DXFPart]:
        """
        Wczytaj detal z pliku DXF.

        Args:
            filepath: Ścieżka do pliku DXF

        Returns:
            DXFPart lub None w przypadku błędu
        """
        if not HAS_EZDXF:
            logger.error("ezdxf not installed - cannot read DXF files")
            return None

        filepath = str(filepath)

        if not os.path.exists(filepath):
            logger.error(f"File not found: {filepath}")
            return None

        try:
            doc = ezdxf.readfile(filepath)
            msp = doc.modelspace()

            # Zbierz wszystkie entities pogrupowane po warstwach
            layer_entities = self._collect_entities(msp)

            # Pobierz informacje o warstwach
            layers_info = self._get_layers_info(doc, layer_entities)

            # Znajdź entities konturu zewnętrznego
            outer_entities = self._find_outer_entities(layer_entities)

            # Znajdź entities otworów
            inner_entities = self._find_inner_entities(layer_entities)

            # Znajdź entities cech (tylko ARCs z IV_FEATURE_PROFILES)
            feature_entities = self._find_feature_entities(layer_entities)

            # Dodaj feature ARCs do outer entities
            outer_entities.extend(feature_entities)

            # Zbuduj kontur zewnętrzny
            outer_contour, _ = build_contours_from_entities(
                outer_entities, self.contour_tolerance
            )

            # Zbuduj otwory
            holes = []
            if inner_entities:
                inner_contours = self._contour_builder.build_contours(inner_entities)
                for contour in inner_contours:
                    contour.is_outer = False
                    holes.append(contour)

            # Sprawdź czy największy CIRCLE powinien być konturem zewnętrznym
            outer_contour = self._check_circle_as_outer(
                outer_contour, layer_entities
            )

            if not outer_contour or len(outer_contour.points) < 3:
                logger.warning(f"Could not build contour from {filepath}")
                return None

            # Parsuj metadane z nazwy
            name = Path(filepath).stem
            material, thickness, quantity = self._parse_filename(name)

            # Oblicz bounding box
            min_x, min_y, max_x, max_y = outer_contour.bounds

            # Oblicz długość cięcia i liczbę przebić
            cut_length = outer_contour.perimeter
            pierce_count = 1  # Kontur zewnętrzny

            for hole in holes:
                cut_length += hole.perimeter
                pierce_count += 1

            # Zbierz wszystkie entities (dla edycji)
            all_entities = outer_entities + inner_entities

            return DXFPart(
                name=name,
                filepath=filepath,
                outer_contour=outer_contour,
                holes=holes,
                entities=all_entities,
                layers=layers_info,
                min_x=min_x,
                max_x=max_x,
                min_y=min_y,
                max_y=max_y,
                material=material,
                thickness=thickness,
                quantity=quantity,
                cut_length_mm=cut_length,
                pierce_count=pierce_count,
            )

        except Exception as e:
            logger.error(f"Error reading DXF {filepath}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _collect_entities(self, msp) -> Dict[str, List[DXFEntity]]:
        """Zbierz entities z modelspace pogrupowane po warstwach"""
        layer_entities: Dict[str, List[DXFEntity]] = {}

        for entity in msp:
            layer = entity.dxf.layer

            if is_ignored_layer(layer):
                continue

            # Konwertuj entity
            dxf_entity = convert_entity(
                entity,
                self.arc_resolution,
                self.spline_tolerance
            )

            if dxf_entity and dxf_entity.points:
                if layer not in layer_entities:
                    layer_entities[layer] = []
                layer_entities[layer].append(dxf_entity)

        return layer_entities

    def _get_layers_info(
        self, doc, layer_entities: Dict[str, List[DXFEntity]]
    ) -> Dict[str, LayerInfo]:
        """Pobierz informacje o warstwach"""
        layers_info: Dict[str, LayerInfo] = {}

        try:
            for layer in doc.layers:
                name = layer.dxf.name
                color = layer.dxf.color if hasattr(layer.dxf, 'color') else 7

                entity_count = len(layer_entities.get(name, []))

                layers_info[name] = LayerInfo(
                    name=name,
                    color=color,
                    entity_count=entity_count,
                    display_color=self._aci_to_hex(color)
                )
        except Exception as e:
            logger.debug(f"Error getting layers: {e}")

        return layers_info

    def _find_outer_entities(
        self, layer_entities: Dict[str, List[DXFEntity]]
    ) -> List[DXFEntity]:
        """Znajdź entities należące do konturu zewnętrznego"""
        outer_entities: List[DXFEntity] = []

        # Posortuj warstwy według priorytetu
        sorted_layers = sorted(
            layer_entities.keys(),
            key=lambda l: get_layer_priority(l)
        )

        # Najpierw szukaj w preferowanych warstwach zewnętrznych
        for layer in sorted_layers:
            if is_outer_layer(layer):
                entities = layer_entities[layer]
                # Filtruj tylko geometrię (nie tekst, wymiary)
                geometry = [
                    e for e in entities
                    if e.entity_type in (
                        EntityType.LINE, EntityType.ARC, EntityType.CIRCLE,
                        EntityType.LWPOLYLINE, EntityType.POLYLINE,
                        EntityType.SPLINE, EntityType.ELLIPSE
                    )
                ]
                if geometry:
                    outer_entities = geometry
                    logger.debug(f"Using outer layer: {layer} ({len(geometry)} entities)")
                    break

        # Jeśli nie znaleziono, użyj wszystkich nie-ignorowanych, nie-inner warstw
        if not outer_entities:
            for layer, entities in layer_entities.items():
                if not is_inner_layer(layer) and not is_feature_layer(layer):
                    geometry = [
                        e for e in entities
                        if e.entity_type in (
                            EntityType.LINE, EntityType.ARC,
                            EntityType.LWPOLYLINE, EntityType.POLYLINE,
                            EntityType.SPLINE, EntityType.ELLIPSE
                        )
                    ]
                    outer_entities.extend(geometry)

        return outer_entities

    def _find_inner_entities(
        self, layer_entities: Dict[str, List[DXFEntity]]
    ) -> List[DXFEntity]:
        """Znajdź entities należące do otworów"""
        inner_entities: List[DXFEntity] = []

        for layer, entities in layer_entities.items():
            if is_inner_layer(layer):
                # Wszystkie CIRCLE i zamknięte figury to otwory
                for entity in entities:
                    if entity.entity_type == EntityType.CIRCLE:
                        inner_entities.append(entity)
                    elif entity.is_closed:
                        inner_entities.append(entity)

        return inner_entities

    def _find_feature_entities(
        self, layer_entities: Dict[str, List[DXFEntity]]
    ) -> List[DXFEntity]:
        """
        Znajdź entities z warstw cech specjalnych.
        Dla IV_FEATURE_PROFILES: tylko ARCs (bend relief cuts), nie LINEs (bend lines).
        """
        feature_entities: List[DXFEntity] = []

        for layer, entities in layer_entities.items():
            if is_feature_layer(layer):
                for entity in entities:
                    # Tylko ARCs - wycięcia przy zgięciach
                    if entity.entity_type == EntityType.ARC:
                        feature_entities.append(entity)
                    # LINEs to linie zgięcia - ignoruj

        return feature_entities

    def _check_circle_as_outer(
        self,
        current_outer: Optional[DXFContour],
        layer_entities: Dict[str, List[DXFEntity]]
    ) -> Optional[DXFContour]:
        """
        Sprawdź czy największy CIRCLE powinien być konturem zewnętrznym.
        Dla detali typu podkładka z otworami.
        """
        # Zbierz wszystkie okręgi
        circles = []
        for entities in layer_entities.values():
            for entity in entities:
                if entity.entity_type == EntityType.CIRCLE:
                    circles.append(entity)

        if not circles:
            return current_outer

        # Znajdź największy okrąg
        largest_circle = max(circles, key=lambda c: c.raw_data.get('radius', 0))
        largest_radius = largest_circle.raw_data.get('radius', 0)
        largest_diameter = largest_radius * 2

        # Porównaj z obecnym konturem
        if current_outer and current_outer.points:
            bounds = current_outer.bounds
            contour_width = bounds[2] - bounds[0]
            contour_height = bounds[3] - bounds[1]
            contour_max_dim = max(contour_width, contour_height)

            # Jeśli okrąg jest znacznie większy, użyj go jako konturu
            if largest_diameter > contour_max_dim * 1.5:
                logger.info(
                    f"Using CIRCLE (r={largest_radius:.2f}mm) as outer contour "
                    f"instead of built contour ({contour_max_dim:.2f}mm)"
                )
                return DXFContour(
                    points=largest_circle.points,
                    entities=[largest_circle],
                    is_closed=True,
                    is_outer=True,
                    layer=largest_circle.layer
                )
        elif not current_outer or len(current_outer.points) < 3:
            # Brak konturu - użyj największego okręgu
            return DXFContour(
                points=largest_circle.points,
                entities=[largest_circle],
                is_closed=True,
                is_outer=True,
                layer=largest_circle.layer
            )

        return current_outer

    def _parse_filename(self, name: str) -> Tuple[str, Optional[float], int]:
        """
        Parsuj metadane z nazwy pliku.

        Format: 11-067608_1,5mm_INOX_1szt

        Returns:
            (material, thickness, quantity)
        """
        material = ""
        thickness = None
        quantity = 1

        name_lower = name.lower()

        # Parse quantity (XXszt)
        qty_match = re.search(r'(\d+)\s*szt', name_lower)
        if qty_match:
            try:
                quantity = int(qty_match.group(1))
            except:
                pass

        # Parse thickness (#XXmm or X,Xmm or X.Xmm)
        # Format #XXmm
        hash_match = re.search(r'#(\d+(?:[.,]\d+)?)\s*mm', name, re.IGNORECASE)
        if hash_match:
            try:
                t = float(hash_match.group(1).replace(',', '.'))
                if 0.5 <= t <= 30:
                    thickness = t
            except:
                pass

        # Format _XXmm_ lub -XXmm
        if thickness is None:
            for part in name.replace('-', '_').split('_'):
                part_lower = part.lower()
                if 'mm' in part_lower:
                    try:
                        t_str = part_lower.replace('mm', '').replace('#', '').replace(',', '.')
                        t = float(t_str.strip())
                        if 0.5 <= t <= 30:
                            thickness = t
                            break
                    except:
                        pass

        # Parse material
        if '1.4301' in name_lower or 'inox' in name_lower or '4301' in name_lower:
            material = '1.4301'
        elif 'superlustro' in name_lower or 'super lustro' in name_lower or 'mirror' in name_lower:
            material = '1.4301'  # Superlustro = INOX mirror
        elif 's235' in name_lower or '_fe_' in name_lower or 'stal' in name_lower:
            material = 'S235'
        elif 'st42' in name_lower or '42crmo4' in name_lower or '42crm04' in name_lower:
            material = '42CrMo4'
        elif 'al' in name_lower.split('_') or 'aluminium' in name_lower:
            material = 'AL'

        return material, thickness, quantity

    def _aci_to_hex(self, aci: int) -> str:
        """Konwertuj ACI color index na hex"""
        # Podstawowe kolory ACI
        aci_colors = {
            0: "#000000",   # ByBlock
            1: "#FF0000",   # Red
            2: "#FFFF00",   # Yellow
            3: "#00FF00",   # Green
            4: "#00FFFF",   # Cyan
            5: "#0000FF",   # Blue
            6: "#FF00FF",   # Magenta
            7: "#FFFFFF",   # White/Black
            8: "#808080",   # Gray
            9: "#C0C0C0",   # Light Gray
            256: "#FFFFFF", # ByLayer
        }
        return aci_colors.get(aci, "#FFFFFF")

    def get_layer_info(self, filepath: str) -> Dict[str, LayerInfo]:
        """
        Pobierz informacje o warstwach z pliku DXF.

        Args:
            filepath: Ścieżka do pliku DXF

        Returns:
            Słownik nazwa_warstwy -> LayerInfo
        """
        if not HAS_EZDXF:
            return {}

        try:
            doc = ezdxf.readfile(filepath)
            msp = doc.modelspace()
            layer_entities = self._collect_entities(msp)
            return self._get_layers_info(doc, layer_entities)
        except Exception as e:
            logger.error(f"Error getting layer info: {e}")
            return {}


# Funkcja pomocnicza dla kompatybilności
def load_dxf(filepath: str, arc_resolution: int = 8) -> Optional[DXFPart]:
    """
    Wczytaj DXF - funkcja kompatybilności z dxf_loader.py

    Args:
        filepath: Ścieżka do pliku DXF
        arc_resolution: Rozdzielczość łuków

    Returns:
        DXFPart lub None
    """
    reader = UnifiedDXFReader(arc_resolution=arc_resolution)
    return reader.read(filepath)


# Eksporty
__all__ = [
    'UnifiedDXFReader',
    'load_dxf',
]
