#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ThumbnailGenerator - Generowanie miniatur i analiza wymiarów z plików CAD

Obsługiwane formaty:
- DXF/DWG (2D) - przez ezdxf + matplotlib lub VTK
- STEP/STP/IGES (3D) - przez CadQuery + VTK (offscreen rendering)
- STL/OBJ (3D mesh) - przez VTK
- Obrazy (PNG/JPG) - przez Pillow

Dodatkowo wyciąga wymiary gabarytu:
- 2D: width_mm, height_mm
- 3D: width_mm, height_mm, length_mm + opcjonalnie masa

Bazuje na sprawdzonym kodzie z STEP_IGES_3D_Viewer.py

Użycie:
    from products.utils.thumbnail_generator import ThumbnailGenerator
    
    generator = ThumbnailGenerator()
    
    # Generuj miniatury
    thumbnails = generator.generate(file_bytes, extension='dxf')
    # -> {'thumbnail_100': bytes, 'preview_800': bytes}
    
    # Pobierz wymiary
    dimensions = generator.get_dimensions(file_bytes, extension='step')
    # -> {'width_mm': 29.794, 'height_mm': 18.5, 'length_mm': 14.149}
"""

import io
import os
import sys
import math
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple, Any
from PIL import Image

from config.settings import THUMBNAIL_SIZES


class ThumbnailGenerator:
    """
    Generator miniatur i analizator wymiarów z plików CAD.
    
    Generuje 2 rozmiary miniatur:
    - thumbnail_100: 100px (do list)
    - preview_800: 800px (podgląd)
    
    Wyciąga wymiary gabarytu z plików CAD.
    """
    
    def __init__(self):
        """Inicjalizacja generatora"""
        self.sizes = THUMBNAIL_SIZES
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Sprawdź dostępność bibliotek"""
        self._has_ezdxf = False
        self._has_matplotlib = False
        self._has_vtk = False
        self._has_cadquery = False
        
        try:
            import ezdxf
            self._has_ezdxf = True
        except ImportError:
            print("[THUMB] ⚠️ ezdxf niedostępny - brak obsługi DXF")
        
        try:
            import matplotlib
            matplotlib.use('Agg')  # Backend bez GUI
            self._has_matplotlib = True
        except ImportError:
            print("[THUMB] ⚠️ matplotlib niedostępny")
        
        try:
            import vtkmodules.all
            self._has_vtk = True
        except ImportError:
            try:
                import vtk
                self._has_vtk = True
            except ImportError:
                print("[THUMB] ⚠️ VTK niedostępny - ograniczone renderowanie 3D")
        
        try:
            import cadquery as cq
            self._has_cadquery = True
        except ImportError:
            print("[THUMB] ⚠️ CadQuery niedostępny - brak obsługi STEP/IGES")
    
    # =========================================================
    # PUBLIC API - MINIATURY
    # =========================================================
    
    def generate(
        self, 
        file_data: bytes, 
        extension: str,
        background_color: Tuple[int, int, int] = (255, 255, 255)
    ) -> Dict[str, bytes]:
        """
        Generuj miniatury z pliku CAD.
        
        Args:
            file_data: Dane pliku jako bytes
            extension: Rozszerzenie pliku (dxf, step, stp, png, jpg, etc.)
            background_color: Kolor tła RGB (domyślnie biały)
            
        Returns:
            Słownik {nazwa: bytes} z miniaturami w formacie PNG
        """
        ext = extension.lower().lstrip('.')
        
        # Pliki 2D CAD
        if ext in ('dxf', 'dwg'):
            return self._generate_from_dxf(file_data, background_color)
        
        # Pliki 3D CAD (STEP/IGES)
        if ext in ('step', 'stp', 'iges', 'igs'):
            return self._generate_from_step(file_data, background_color)
        
        # Pliki 3D mesh
        if ext in ('stl', 'obj', '3mf'):
            return self._generate_from_stl(file_data, ext, background_color)
        
        # Obrazy
        if ext in ('png', 'jpg', 'jpeg', 'bmp', 'gif', 'webp', 'tiff'):
            return self._generate_from_image(file_data)
        
        print(f"[THUMB] ⚠️ Nieobsługiwany format: {ext}")
        return {}
    
    # =========================================================
    # PUBLIC API - WYMIARY
    # =========================================================
    
    def get_dimensions(
        self, 
        file_data: bytes, 
        extension: str,
        material_density: float = None
    ) -> Dict[str, float]:
        """
        Pobierz wymiary gabarytu z pliku CAD.
        
        Args:
            file_data: Dane pliku jako bytes
            extension: Rozszerzenie pliku
            material_density: Gęstość materiału kg/m³ (dla obliczeń masy 3D)
            
        Returns:
            Słownik z wymiarami:
            - 2D: {'width_mm': float, 'height_mm': float}
            - 3D: {'width_mm': float, 'height_mm': float, 'length_mm': float, 
                   'volume_mm3': float, 'weight_kg': float (jeśli podano gęstość)}
        """
        ext = extension.lower().lstrip('.')
        
        if ext in ('dxf', 'dwg'):
            return self._get_dxf_dimensions(file_data)
        
        if ext in ('step', 'stp', 'iges', 'igs'):
            return self._get_step_dimensions(file_data, material_density)
        
        if ext in ('stl', 'obj', '3mf'):
            return self._get_stl_dimensions(file_data, ext)
        
        return {}
    
    # =========================================================
    # DXF - MINIATURY I WYMIARY
    # =========================================================
    
    def _generate_from_dxf(
        self, 
        dxf_data: bytes,
        background_color: Tuple[int, int, int]
    ) -> Dict[str, bytes]:
        """Generuj miniatury z pliku DXF używając matplotlib (BEZ ezdxf.addons.drawing)"""
        
        print(f"[THUMB] 🔍 _generate_from_dxf called, data size: {len(dxf_data)} bytes")
        
        if not self._has_ezdxf or not self._has_matplotlib:
            return {}
        
        try:
            import ezdxf
            import matplotlib.pyplot as plt
            import numpy as np
            
            # Zapisz do pliku tymczasowego
            with tempfile.NamedTemporaryFile(suffix='.dxf', delete=False) as tmp:
                tmp.write(dxf_data)
                tmp_path = tmp.name
            
            try:
                doc = ezdxf.readfile(tmp_path)
                msp = doc.modelspace()
                
                # Zbierz geometrię
                all_points = []
                segments = []  # Lista (start, end) dla linii
                
                for entity in msp:
                    entity_type = entity.dxftype()
                    
                    if entity_type == 'LINE':
                        start = (entity.dxf.start.x, entity.dxf.start.y)
                        end = (entity.dxf.end.x, entity.dxf.end.y)
                        segments.append((start, end))
                        all_points.extend([start, end])
                    
                    elif entity_type == 'LWPOLYLINE':
                        points = list(entity.get_points(format='xy'))
                        for i in range(len(points) - 1):
                            segments.append((points[i], points[i+1]))
                        if entity.closed and len(points) > 1:
                            segments.append((points[-1], points[0]))
                        all_points.extend(points)
                    
                    elif entity_type == 'POLYLINE':
                        points = [(v.dxf.location.x, v.dxf.location.y) 
                                  for v in entity.vertices if hasattr(v, 'dxf')]
                        for i in range(len(points) - 1):
                            segments.append((points[i], points[i+1]))
                        if entity.is_closed and len(points) > 1:
                            segments.append((points[-1], points[0]))
                        all_points.extend(points)
                    
                    elif entity_type == 'CIRCLE':
                        cx, cy = entity.dxf.center.x, entity.dxf.center.y
                        r = entity.dxf.radius
                        # Aproksymacja okręgu
                        n_seg = 48
                        circle_pts = []
                        for i in range(n_seg):
                            angle = 2 * math.pi * i / n_seg
                            pt = (cx + r * math.cos(angle), cy + r * math.sin(angle))
                            circle_pts.append(pt)
                        for i in range(n_seg):
                            segments.append((circle_pts[i], circle_pts[(i+1) % n_seg]))
                        all_points.extend(circle_pts)
                    
                    elif entity_type == 'ARC':
                        cx, cy = entity.dxf.center.x, entity.dxf.center.y
                        r = entity.dxf.radius
                        start_angle = math.radians(entity.dxf.start_angle)
                        end_angle = math.radians(entity.dxf.end_angle)
                        if end_angle < start_angle:
                            end_angle += 2 * math.pi
                        
                        angle_span = end_angle - start_angle
                        n_seg = max(int(48 * angle_span / (2 * math.pi)), 4)
                        arc_pts = []
                        for i in range(n_seg + 1):
                            angle = start_angle + angle_span * i / n_seg
                            pt = (cx + r * math.cos(angle), cy + r * math.sin(angle))
                            arc_pts.append(pt)
                        for i in range(len(arc_pts) - 1):
                            segments.append((arc_pts[i], arc_pts[i+1]))
                        all_points.extend(arc_pts)
                    
                    elif entity_type == 'SPLINE':
                        try:
                            # Próbuj pobrać punkty kontrolne lub fit points
                            points = list(entity.flattening(0.1))  # Segmentacja spline
                            pts = [(p.x, p.y) for p in points]
                            for i in range(len(pts) - 1):
                                segments.append((pts[i], pts[i+1]))
                            all_points.extend(pts)
                        except Exception:
                            pass
                    
                    elif entity_type == 'ELLIPSE':
                        try:
                            # Aproksymacja elipsy
                            cx, cy = entity.dxf.center.x, entity.dxf.center.y
                            major = entity.dxf.major_axis
                            ratio = entity.dxf.ratio
                            n_seg = 48
                            ellipse_pts = []
                            for i in range(n_seg):
                                angle = 2 * math.pi * i / n_seg
                                # Uproszczenie - zakładamy elipsę wyrównaną do osi
                                a = math.sqrt(major.x**2 + major.y**2)
                                b = a * ratio
                                pt = (cx + a * math.cos(angle), cy + b * math.sin(angle))
                                ellipse_pts.append(pt)
                            for i in range(n_seg):
                                segments.append((ellipse_pts[i], ellipse_pts[(i+1) % n_seg]))
                            all_points.extend(ellipse_pts)
                        except Exception:
                            pass
                
                if not all_points:
                    return {}
                
                # Oblicz bounds
                xs = [p[0] for p in all_points]
                ys = [p[1] for p in all_points]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)
                
                # Margines 5%
                width = max_x - min_x or 1
                height = max_y - min_y or 1
                margin = 0.05
                min_x -= width * margin
                max_x += width * margin
                min_y -= height * margin
                max_y += height * margin
                
                # Rysuj na największy rozmiar
                max_size = self.sizes.get('large', 4096)
                dpi = 150
                fig_size = max_size / dpi
                
                fig, ax = plt.subplots(figsize=(fig_size, fig_size), dpi=dpi)
                
                # Tło
                bg_normalized = tuple(c/255 for c in background_color)
                fig.patch.set_facecolor(bg_normalized)
                ax.set_facecolor(bg_normalized)
                
                # Rysuj segmenty - kolor zależny od tła
                if sum(background_color) > 384:  # Jasne tło
                    line_color = '#000066'  # Ciemnoniebieski
                else:  # Ciemne tło
                    line_color = '#00BFFF'  # Jasnoniebieski (jak w Twoim viewerze)
                
                for start, end in segments:
                    ax.plot([start[0], end[0]], [start[1], end[1]], 
                           color=line_color, linewidth=0.8)
                
                ax.set_xlim(min_x, max_x)
                ax.set_ylim(min_y, max_y)
                ax.set_aspect('equal')
                ax.axis('off')
                
                # Zapisz do bufora
                buf = io.BytesIO()
                fig.savefig(buf, format='png', bbox_inches='tight', 
                           pad_inches=0.02, facecolor=bg_normalized,
                           transparent=False)
                plt.close(fig)
                
                buf.seek(0)
                image = Image.open(buf)
                
                return self._generate_sizes(image)
                
            finally:
                os.unlink(tmp_path)
                
        except Exception as e:
            print(f"[THUMB] ❌ Błąd generowania z DXF: {e}")
            return {}
    
    def _get_dxf_dimensions(self, dxf_data: bytes) -> Dict[str, float]:
        """Pobierz wymiary z pliku DXF"""
        
        if not self._has_ezdxf:
            return {}
        
        try:
            import ezdxf
            
            with tempfile.NamedTemporaryFile(suffix='.dxf', delete=False) as tmp:
                tmp.write(dxf_data)
                tmp_path = tmp.name
            
            try:
                doc = ezdxf.readfile(tmp_path)
                msp = doc.modelspace()
                
                all_x = []
                all_y = []
                
                for entity in msp:
                    entity_type = entity.dxftype()
                    
                    if entity_type == 'LINE':
                        all_x.extend([entity.dxf.start.x, entity.dxf.end.x])
                        all_y.extend([entity.dxf.start.y, entity.dxf.end.y])
                    
                    elif entity_type in ('LWPOLYLINE', 'POLYLINE'):
                        try:
                            for pt in entity.get_points(format='xy'):
                                all_x.append(pt[0])
                                all_y.append(pt[1])
                        except Exception:
                            pass
                    
                    elif entity_type == 'CIRCLE':
                        cx, cy = entity.dxf.center.x, entity.dxf.center.y
                        r = entity.dxf.radius
                        all_x.extend([cx - r, cx + r])
                        all_y.extend([cy - r, cy + r])
                    
                    elif entity_type == 'ARC':
                        cx, cy = entity.dxf.center.x, entity.dxf.center.y
                        r = entity.dxf.radius
                        all_x.extend([cx - r, cx + r])
                        all_y.extend([cy - r, cy + r])
                
                if all_x and all_y:
                    return {
                        'width_mm': round(max(all_x) - min(all_x), 3),
                        'height_mm': round(max(all_y) - min(all_y), 3),
                    }
                
            finally:
                os.unlink(tmp_path)
                
        except Exception as e:
            print(f"[THUMB] ❌ Błąd pobierania wymiarów DXF: {e}")
        
        return {}
    
    # =========================================================
    # STEP/IGES - MINIATURY I WYMIARY
    # =========================================================
    
    def _generate_from_step(
        self, 
        step_data: bytes,
        background_color: Tuple[int, int, int]
    ) -> Dict[str, bytes]:
        """Generuj miniatury z pliku STEP używając CadQuery + VTK"""
        
        if not self._has_cadquery or not self._has_vtk:
            return {}
        
        try:
            import cadquery as cq
            
            # Zapisz STEP do pliku tymczasowego
            with tempfile.NamedTemporaryFile(suffix='.step', delete=False) as tmp:
                tmp.write(step_data)
                step_path = tmp.name
            
            stl_path = step_path.replace('.step', '.stl')
            
            try:
                # Import STEP i eksport do STL
                shape = cq.importers.importStep(step_path)
                cq.exporters.export(shape, stl_path, tolerance=0.1, angularTolerance=0.1)
                
                # Renderuj STL do obrazu
                with open(stl_path, 'rb') as f:
                    stl_data = f.read()
                
                return self._render_stl_to_image(stl_data, background_color)
                
            finally:
                if os.path.exists(step_path):
                    os.unlink(step_path)
                if os.path.exists(stl_path):
                    os.unlink(stl_path)
                    
        except Exception as e:
            print(f"[THUMB] ❌ Błąd generowania z STEP: {e}")
            return {}
    
    def _get_step_dimensions(
        self, 
        step_data: bytes, 
        material_density: float = None
    ) -> Dict[str, float]:
        """Pobierz wymiary i objętość z pliku STEP"""
        
        if not self._has_cadquery:
            return {}
        
        try:
            import cadquery as cq
            
            with tempfile.NamedTemporaryFile(suffix='.step', delete=False) as tmp:
                tmp.write(step_data)
                step_path = tmp.name
            
            try:
                shape = cq.importers.importStep(step_path)
                
                # Bounding box
                bb = shape.val().BoundingBox()
                
                result = {
                    'width_mm': round(bb.xlen, 3),
                    'height_mm': round(bb.ylen, 3),
                    'length_mm': round(bb.zlen, 3),
                }
                
                # Objętość (jeśli to solid)
                try:
                    # CadQuery zwraca objętość w mm³
                    volume = shape.val().Volume()
                    result['volume_mm3'] = round(volume, 3)
                    
                    # Masa jeśli podano gęstość
                    if material_density and volume > 0:
                        # volume w mm³, density w kg/m³
                        # 1 m³ = 10^9 mm³
                        mass_kg = (volume / 1e9) * material_density
                        result['weight_kg'] = round(mass_kg, 4)
                        
                except Exception:
                    pass
                
                return result
                
            finally:
                os.unlink(step_path)
                
        except Exception as e:
            print(f"[THUMB] ❌ Błąd pobierania wymiarów STEP: {e}")
        
        return {}
    
    # =========================================================
    # STL - MINIATURY I WYMIARY
    # =========================================================
    
    def _generate_from_stl(
        self, 
        stl_data: bytes,
        extension: str,
        background_color: Tuple[int, int, int]
    ) -> Dict[str, bytes]:
        """Generuj miniatury z pliku STL/OBJ"""
        return self._render_stl_to_image(stl_data, background_color, extension)
    
    def _render_stl_to_image(
        self, 
        stl_data: bytes,
        background_color: Tuple[int, int, int],
        extension: str = 'stl'
    ) -> Dict[str, bytes]:
        """Renderuj mesh do obrazu używając VTK (offscreen)"""
        
        if not self._has_vtk:
            return {}
        
        try:
            from vtkmodules.vtkIOGeometry import vtkSTLReader, vtkOBJReader
            from vtkmodules.vtkRenderingCore import (
                vtkRenderer, vtkRenderWindow, vtkPolyDataMapper, vtkActor
            )
            from vtkmodules.vtkFiltersCore import vtkPolyDataNormals
            from vtkmodules.vtkIOImage import vtkPNGWriter
            from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
            
            # Zapisz do pliku tymczasowego
            with tempfile.NamedTemporaryFile(suffix=f'.{extension}', delete=False) as tmp:
                tmp.write(stl_data)
                tmp_path = tmp.name
            
            try:
                # Wczytaj mesh
                if extension.lower() in ('stl',):
                    reader = vtkSTLReader()
                elif extension.lower() in ('obj',):
                    reader = vtkOBJReader()
                else:
                    reader = vtkSTLReader()
                
                reader.SetFileName(tmp_path)
                reader.Update()
                
                # Normalne dla gładkiego cieniowania
                normals = vtkPolyDataNormals()
                normals.SetInputConnection(reader.GetOutputPort())
                normals.ComputePointNormalsOn()
                normals.ComputeCellNormalsOff()
                normals.SplittingOff()  # Unikaj artefaktów
                normals.Update()
                
                # Mapper i Actor
                mapper = vtkPolyDataMapper()
                mapper.SetInputConnection(normals.GetOutputPort())
                
                actor = vtkActor()
                actor.SetMapper(mapper)
                # Kolor podobny do Twojego viewera (jasny szary/niebieski)
                actor.GetProperty().SetColor(0.85, 0.87, 0.90)
                actor.GetProperty().SetAmbient(0.3)
                actor.GetProperty().SetDiffuse(0.7)
                actor.GetProperty().SetSpecular(0.2)
                
                # Renderer
                renderer = vtkRenderer()
                renderer.AddActor(actor)
                bg = tuple(c/255 for c in background_color)
                renderer.SetBackground(*bg)
                
                # Kamera - widok izometryczny
                renderer.ResetCamera()
                camera = renderer.GetActiveCamera()
                camera.Azimuth(45)
                camera.Elevation(30)
                renderer.ResetCamera()
                
                # Render window (offscreen)
                render_window = vtkRenderWindow()
                render_window.SetOffScreenRendering(1)
                render_window.AddRenderer(renderer)
                
                # Renderuj w największym rozmiarze
                max_size = self.sizes.get('large', 4096)
                render_window.SetSize(max_size, max_size)
                render_window.Render()
                
                # Zapisz do obrazu
                w2i = vtkWindowToImageFilter()
                w2i.SetInput(render_window)
                w2i.ReadFrontBufferOff()
                w2i.Update()
                
                # Zapisz do PNG w pamięci
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as png_tmp:
                    png_path = png_tmp.name
                
                writer = vtkPNGWriter()
                writer.SetFileName(png_path)
                writer.SetInputConnection(w2i.GetOutputPort())
                writer.Write()
                
                # Wczytaj jako PIL Image
                image = Image.open(png_path)
                image.load()  # Wymuś wczytanie do pamięci
                
                # Skopiuj obraz do pamięci przed zamknięciem pliku
                image_copy = image.copy()
                image.close()
                
                # Cleanup - z obsługą Windows file lock
                render_window.Finalize()
                
                # Poczekaj chwilę i usuń plik
                import time
                time.sleep(0.1)
                try:
                    os.unlink(png_path)
                except PermissionError:
                    pass  # Plik zostanie usunięty później
                
                return self._generate_sizes(image_copy)
                
            finally:
                os.unlink(tmp_path)
                
        except Exception as e:
            print(f"[THUMB] ❌ Błąd renderowania STL: {e}")
            return {}
    
    def _get_stl_dimensions(self, stl_data: bytes, extension: str) -> Dict[str, float]:
        """Pobierz wymiary z pliku STL"""
        
        if not self._has_vtk:
            return {}
        
        try:
            from vtkmodules.vtkIOGeometry import vtkSTLReader
            
            with tempfile.NamedTemporaryFile(suffix=f'.{extension}', delete=False) as tmp:
                tmp.write(stl_data)
                tmp_path = tmp.name
            
            try:
                reader = vtkSTLReader()
                reader.SetFileName(tmp_path)
                reader.Update()
                
                bounds = reader.GetOutput().GetBounds()
                # bounds = (xmin, xmax, ymin, ymax, zmin, zmax)
                
                return {
                    'width_mm': round(bounds[1] - bounds[0], 3),
                    'height_mm': round(bounds[3] - bounds[2], 3),
                    'length_mm': round(bounds[5] - bounds[4], 3),
                }
                
            finally:
                os.unlink(tmp_path)
                
        except Exception as e:
            print(f"[THUMB] ❌ Błąd pobierania wymiarów STL: {e}")
        
        return {}
    
    # =========================================================
    # OBRAZY
    # =========================================================
    
    def _generate_from_image(self, image_data: bytes) -> Dict[str, bytes]:
        """Generuj miniatury z obrazu"""
        try:
            image = Image.open(io.BytesIO(image_data))
            
            # Konwertuj do RGB jeśli potrzeba
            if image.mode not in ('RGB', 'RGBA'):
                image = image.convert('RGBA')
            
            return self._generate_sizes(image)
            
        except Exception as e:
            print(f"[THUMB] ❌ Błąd generowania z obrazu: {e}")
            return {}
    
    # =========================================================
    # HELPERS
    # =========================================================
    
    def _generate_sizes(self, image: Image.Image) -> Dict[str, bytes]:
        """Generuj wszystkie rozmiary miniatur z obrazu PIL"""
        results = {}
        
        size_mapping = {
            'thumbnail_100': self.sizes.get('small', 100),
            'preview_800': self.sizes.get('medium', 800),
        }
        
        for name, size in size_mapping.items():
            try:
                thumb = image.copy()
                thumb.thumbnail((size, size), Image.Resampling.LANCZOS)
                
                buffer = io.BytesIO()
                
                if thumb.mode == 'RGBA':
                    thumb.save(buffer, format='PNG', optimize=True)
                else:
                    if thumb.mode != 'RGB':
                        thumb = thumb.convert('RGB')
                    thumb.save(buffer, format='PNG', optimize=True)
                
                results[name] = buffer.getvalue()
                
            except Exception as e:
                print(f"[THUMB] ⚠️ Błąd generowania {name}: {e}")
        
        return results


# =========================================================
# FACTORY
# =========================================================

def create_thumbnail_generator() -> ThumbnailGenerator:
    """Utwórz instancję ThumbnailGenerator"""
    return ThumbnailGenerator()


# =========================================================
# TEST
# =========================================================

if __name__ == "__main__":
    print("=" * 60)
    print("ThumbnailGenerator - Test")
    print("=" * 60)
    
    gen = ThumbnailGenerator()
    
    print(f"\nDostępne biblioteki:")
    print(f"  ezdxf:     {'✅' if gen._has_ezdxf else '❌'}")
    print(f"  matplotlib: {'✅' if gen._has_matplotlib else '❌'}")
    print(f"  VTK:       {'✅' if gen._has_vtk else '❌'}")
    print(f"  CadQuery:  {'✅' if gen._has_cadquery else '❌'}")
    
    print(f"\nRozmiary miniatur:")
    for name, size in gen.sizes.items():
        print(f"  {name}: {size}px")
    
    print(f"\nObsługiwane formaty:")
    print(f"  2D: DXF, DWG (wymaga ezdxf + matplotlib)")
    print(f"  3D: STEP, STP, IGES, IGS (wymaga CadQuery + VTK)")
    print(f"  Mesh: STL, OBJ (wymaga VTK)")
    print(f"  Obrazy: PNG, JPG, BMP, GIF, WEBP, TIFF")
