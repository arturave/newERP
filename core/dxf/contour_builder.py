"""
DXF Contour Builder - Budowanie zamkniętych konturów z entities
===============================================================
Kluczowy moduł łączący LINE, ARC, CIRCLE etc. w zamknięte kontury.
Bazuje na sprawdzonym algorytmie z dxf_loader.py
"""

import math
import logging
from typing import List, Tuple, Optional, Set
from collections import defaultdict

from .entities import DXFEntity, DXFContour, EntityType

logger = logging.getLogger(__name__)


def distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Odległość między dwoma punktami"""
    return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)


class ContourBuilder:
    """
    Buduje zamknięte kontury z luźnych entities DXF.

    Algorytm:
    1. Konwertuje każdą entity na segment (start, end, points)
    2. Łączy segmenty end-to-start z tolerancją
    3. Grupuje w zamknięte kontury
    """

    def __init__(self, tolerance_mm: float = 1.0):
        """
        Args:
            tolerance_mm: Tolerancja łączenia punktów końcowych (mm)
        """
        self.tolerance = tolerance_mm

    def build_contours(self, entities: List[DXFEntity]) -> List[DXFContour]:
        """
        Zbuduj zamknięte kontury z listy entities.

        Args:
            entities: Lista DXFEntity do połączenia

        Returns:
            Lista DXFContour (zamknięte kontury)
        """
        if not entities:
            return []

        # Rozdziel entities na zamknięte figury i segmenty do łączenia
        closed_contours = []
        open_segments = []

        for entity in entities:
            if entity.is_closed and len(entity.points) >= 3:
                # Zamknięta figura (CIRCLE, zamknięty LWPOLYLINE)
                contour = DXFContour(
                    points=list(entity.points),
                    entities=[entity],
                    is_closed=True,
                    layer=entity.layer
                )
                closed_contours.append(contour)
            elif entity.points and len(entity.points) >= 2:
                # Otwarty segment do łączenia
                open_segments.append(entity)

        # Łącz otwarte segmenty w kontury
        if open_segments:
            built_contours = self._build_from_segments(open_segments)
            closed_contours.extend(built_contours)

        return closed_contours

    def _build_from_segments(self, entities: List[DXFEntity]) -> List[DXFContour]:
        """Łącz otwarte segmenty w zamknięte kontury"""

        # Konwertuj entities na segmenty (start, end, entity)
        segments = []
        for entity in entities:
            if entity.points and len(entity.points) >= 2:
                start = entity.points[0]
                end = entity.points[-1]
                segments.append({
                    'start': start,
                    'end': end,
                    'entity': entity,
                    'used': False
                })

        if not segments:
            return []

        contours = []

        # Buduj kontury dopóki są nieużyte segmenty
        while True:
            # Znajdź pierwszy nieużyty segment
            start_idx = None
            for i, seg in enumerate(segments):
                if not seg['used']:
                    start_idx = i
                    break

            if start_idx is None:
                break  # Wszystkie segmenty użyte

            # Rozpocznij nowy kontur
            contour_points = list(segments[start_idx]['entity'].points)
            contour_entities = [segments[start_idx]['entity']]
            segments[start_idx]['used'] = True

            # Rozszerzaj kontur w obie strony
            max_iterations = len(segments) * 2
            iteration = 0

            while iteration < max_iterations:
                iteration += 1
                found = False

                current_start = contour_points[0]
                current_end = contour_points[-1]

                for seg in segments:
                    if seg['used']:
                        continue

                    seg_start = seg['start']
                    seg_end = seg['end']

                    # Sprawdź dopasowanie do końca konturu
                    if distance(current_end, seg_start) < self.tolerance:
                        # Segment pasuje (start -> koniec konturu)
                        contour_points.extend(seg['entity'].points[1:])
                        contour_entities.append(seg['entity'])
                        seg['used'] = True
                        found = True
                        break

                    elif distance(current_end, seg_end) < self.tolerance:
                        # Segment pasuje odwrócony
                        reversed_points = list(reversed(seg['entity'].points))
                        contour_points.extend(reversed_points[1:])
                        contour_entities.append(seg['entity'])
                        seg['used'] = True
                        found = True
                        break

                    # Sprawdź dopasowanie do początku konturu
                    elif distance(current_start, seg_end) < self.tolerance:
                        # Segment pasuje na początek
                        new_points = list(seg['entity'].points[:-1])
                        new_points.extend(contour_points)
                        contour_points = new_points
                        contour_entities.insert(0, seg['entity'])
                        seg['used'] = True
                        found = True
                        break

                    elif distance(current_start, seg_start) < self.tolerance:
                        # Segment pasuje odwrócony na początek
                        reversed_points = list(reversed(seg['entity'].points))
                        new_points = reversed_points[:-1]
                        new_points.extend(contour_points)
                        contour_points = new_points
                        contour_entities.insert(0, seg['entity'])
                        seg['used'] = True
                        found = True
                        break

                if not found:
                    break

            # Sprawdź czy kontur jest zamknięty
            is_closed = False
            if len(contour_points) >= 3:
                if distance(contour_points[0], contour_points[-1]) < self.tolerance:
                    is_closed = True
                    # Zamknij dokładnie
                    if contour_points[-1] != contour_points[0]:
                        contour_points.append(contour_points[0])

            # Utwórz kontur
            layer = contour_entities[0].layer if contour_entities else ""
            contour = DXFContour(
                points=contour_points,
                entities=contour_entities,
                is_closed=is_closed,
                layer=layer
            )
            contours.append(contour)

        return contours

    def find_outer_contour(self, contours: List[DXFContour]) -> Optional[DXFContour]:
        """
        Znajdź kontur zewnętrzny (największe pole powierzchni).

        Args:
            contours: Lista konturów

        Returns:
            Kontur z największym polem lub None
        """
        if not contours:
            return None

        max_area = 0
        outer = None

        for contour in contours:
            area = contour.area
            if area > max_area:
                max_area = area
                outer = contour

        if outer:
            outer.is_outer = True

        return outer

    def classify_contours(self, contours: List[DXFContour]) -> Tuple[Optional[DXFContour], List[DXFContour]]:
        """
        Klasyfikuj kontury na zewnętrzny i otwory.

        Args:
            contours: Lista wszystkich konturów

        Returns:
            (outer_contour, holes) - kontur zewnętrzny i lista otworów
        """
        if not contours:
            return None, []

        # Znajdź największy kontur jako zewnętrzny
        outer = self.find_outer_contour(contours)

        if not outer:
            return None, []

        # Pozostałe to otwory
        holes = []
        for contour in contours:
            if contour is not outer:
                contour.is_outer = False
                holes.append(contour)

        return outer, holes

    def repair_gaps(self, contour: DXFContour, max_gap_mm: float = 2.0) -> DXFContour:
        """
        Napraw przerwy w konturze (łącząc bliskie punkty).

        Args:
            contour: Kontur do naprawy
            max_gap_mm: Maksymalna przerwa do naprawy (mm)

        Returns:
            Naprawiony kontur
        """
        if not contour.points or len(contour.points) < 2:
            return contour

        # Sprawdź czy kontur jest zamknięty
        start = contour.points[0]
        end = contour.points[-1]

        gap = distance(start, end)

        if gap < self.tolerance:
            # Już zamknięty
            contour.is_closed = True
            return contour

        if gap <= max_gap_mm:
            # Zamknij dodając punkt końcowy
            new_points = list(contour.points)
            new_points.append(start)
            return DXFContour(
                points=new_points,
                entities=contour.entities,
                is_closed=True,
                layer=contour.layer
            )

        # Przerwa za duża
        logger.warning(f"Gap too large to repair: {gap:.2f}mm > {max_gap_mm}mm")
        return contour


def build_contours_from_entities(
    entities: List[DXFEntity],
    tolerance_mm: float = 1.0
) -> Tuple[Optional[DXFContour], List[DXFContour]]:
    """
    Funkcja pomocnicza - buduje kontury i klasyfikuje je.

    Args:
        entities: Lista DXFEntity
        tolerance_mm: Tolerancja łączenia

    Returns:
        (outer_contour, holes) - kontur zewnętrzny i lista otworów
    """
    builder = ContourBuilder(tolerance_mm)
    contours = builder.build_contours(entities)
    return builder.classify_contours(contours)


# Eksporty
__all__ = [
    'ContourBuilder',
    'build_contours_from_entities',
    'distance',
]
