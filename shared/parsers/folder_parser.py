"""
NewERP - Folder Parser
======================
Moduł do parsowania folderów z plikami CAD (DXF/DWG, STEP/IGES, PDF).

Obsługuje struktury:
    /Zamówienie/
        /INOX304_2mm/
            12-017118_INOX304_2mm_5szt.dxf
            12-017118_INOX304_2mm_5szt.stp
            12-017118.pdf
        /DC01_3mm/
            ...

Logika grupowania:
- Pliki DXF/DWG → file_2d (główny plik do nestingu)
- Pliki STEP/STP/IGES/IGS → file_3d (źródło thumbnail + analiza gięcia)
- Pliki PDF → attachment (dokumentacja)
- Grupowanie po core_name (rdzeń nazwy bez materiału/grubości/ilości)
"""

import os
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from enum import Enum

# Import parsera nazw
try:
    from shared.parsers.name_parser import (
        parse_filename_with_folder_context,
        parse_filename,
        reload_rules
    )
except ImportError:
    # Fallback dla testów
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / 'shared' / 'parsers'))
    from name_parser import (
        parse_filename_with_folder_context,
        parse_filename,
        reload_rules
    )

logger = logging.getLogger(__name__)


class FileType(Enum):
    """Typ pliku CAD"""
    FILE_2D = "2d"          # DXF, DWG
    FILE_3D = "3d"          # STEP, STP, IGES, IGS
    ATTACHMENT = "attachment"  # PDF
    PREVIEW = "preview"     # PNG, JPG (thumbnail)
    ARCHIVE = "archive"     # ZIP, 7Z, RAR
    OTHER = "other"


# Mapowanie rozszerzeń na typy
EXTENSION_MAP = {
    # 2D CAD
    '.dxf': FileType.FILE_2D,
    '.dwg': FileType.FILE_2D,
    
    # 3D CAD
    '.step': FileType.FILE_3D,
    '.stp': FileType.FILE_3D,
    '.iges': FileType.FILE_3D,
    '.igs': FileType.FILE_3D,
    '.ipt': FileType.FILE_3D,  # Inventor
    '.prt': FileType.FILE_3D,  # NX/Creo
    '.sldprt': FileType.FILE_3D,  # SolidWorks
    
    # Dokumentacja
    '.pdf': FileType.ATTACHMENT,
    
    # Podglądy
    '.png': FileType.PREVIEW,
    '.jpg': FileType.PREVIEW,
    '.jpeg': FileType.PREVIEW,
    
    # Archiwa
    '.zip': FileType.ARCHIVE,
    '.7z': FileType.ARCHIVE,
    '.rar': FileType.ARCHIVE,
}


@dataclass
class ParsedFile:
    """Pojedynczy sparsowany plik"""
    path: Path
    filename: str
    extension: str
    file_type: FileType
    
    # Sparsowane dane
    core_name: str
    material: str
    thickness_mm: Optional[float]
    quantity: Optional[int]
    
    # Rozmiar pliku
    size_bytes: int = 0
    
    def __post_init__(self):
        if self.path.exists():
            self.size_bytes = self.path.stat().st_size


@dataclass
class ProductGroup:
    """
    Grupa plików reprezentująca jeden produkt/detal.
    
    Grupowanie po core_name - wszystkie pliki o tym samym rdzeniu nazwy
    są traktowane jako jeden produkt z różnymi reprezentacjami.
    """
    core_name: str
    material: str
    thickness_mm: Optional[float]
    quantity: Optional[int]
    
    # Pliki (może być wiele wariantów)
    files_2d: List[ParsedFile] = field(default_factory=list)
    files_3d: List[ParsedFile] = field(default_factory=list)
    attachments: List[ParsedFile] = field(default_factory=list)
    previews: List[ParsedFile] = field(default_factory=list)
    
    # Operacje
    has_bending: bool = False  # Czy wymaga gięcia (na podstawie 3D)
    
    @property
    def primary_2d(self) -> Optional[ParsedFile]:
        """Główny plik 2D (preferuj DXF)"""
        dxf = [f for f in self.files_2d if f.extension == '.dxf']
        if dxf:
            return dxf[0]
        return self.files_2d[0] if self.files_2d else None
    
    @property
    def primary_3d(self) -> Optional[ParsedFile]:
        """Główny plik 3D (preferuj STEP)"""
        step = [f for f in self.files_3d if f.extension in ('.step', '.stp')]
        if step:
            return step[0]
        return self.files_3d[0] if self.files_3d else None
    
    @property
    def primary_attachment(self) -> Optional[ParsedFile]:
        """Główny załącznik (PDF)"""
        return self.attachments[0] if self.attachments else None
    
    @property
    def thumbnail_source(self) -> Optional[ParsedFile]:
        """Źródło dla thumbnails - preview > 3D > 2D"""
        if self.previews:
            return self.previews[0]
        if self.files_3d:
            return self.primary_3d
        return self.primary_2d
    
    # Wielokąt (dla zaawansowanego nestingu)
    _polygon_cache: Optional[object] = field(default=None, repr=False)
    
    def get_polygon(self) -> Optional[object]:
        """
        Pobierz wielokąt z pliku DXF (dla zaawansowanego nestingu NFP).
        
        Returns:
            DXFPolygon lub None jeśli brak pliku DXF lub błąd ekstrakcji
        """
        if self._polygon_cache is not None:
            return self._polygon_cache
        
        if not self.primary_2d or self.primary_2d.extension != '.dxf':
            return None
        
        try:
            from quotations.nesting.dxf_polygon import get_dxf_polygon
            self._polygon_cache = get_dxf_polygon(self.primary_2d.path)
            return self._polygon_cache
        except ImportError:
            return None
        except Exception:
            return None
    
    @property
    def display_name(self) -> str:
        """Nazwa wyświetlana"""
        parts = [self.core_name]
        if self.material:
            parts.append(self.material)
        if self.thickness_mm:
            parts.append(f"{self.thickness_mm}mm")
        return " | ".join(parts)
    
    def to_product_dict(self) -> Dict:
        """Konwertuj do formatu produktu NewERP"""
        return {
            'name': self.core_name,
            'code': self.core_name,
            'material': self.material,
            'thickness_mm': self.thickness_mm,
            'quantity': self.quantity or 1,
            'has_bending': self.has_bending,
            # Ścieżki plików do uploadu
            '_file_2d_path': str(self.primary_2d.path) if self.primary_2d else None,
            '_file_3d_path': str(self.primary_3d.path) if self.primary_3d else None,
            '_attachment_path': str(self.primary_attachment.path) if self.primary_attachment else None,
            '_thumbnail_source': str(self.thumbnail_source.path) if self.thumbnail_source else None,
        }


@dataclass
class FolderScanResult:
    """Wynik skanowania folderu"""
    root_path: Path
    total_files: int
    parsed_files: List[ParsedFile]
    product_groups: List[ProductGroup]
    
    # Statystyki
    materials_found: Set[str] = field(default_factory=set)
    thicknesses_found: Set[float] = field(default_factory=set)
    
    # Błędy
    errors: List[str] = field(default_factory=list)
    
    @property
    def summary(self) -> str:
        """Podsumowanie tekstowe"""
        return (
            f"Folder: {self.root_path.name}\n"
            f"Plików: {self.total_files}\n"
            f"Produktów: {len(self.product_groups)}\n"
            f"Materiały: {', '.join(sorted(self.materials_found)) or 'brak'}\n"
            f"Grubości: {', '.join(f'{t}mm' for t in sorted(self.thicknesses_found)) or 'brak'}"
        )


class FolderParser:
    """
    Parser folderów z plikami CAD.
    
    Użycie:
        parser = FolderParser()
        result = parser.scan_folder("/path/to/order")
        
        for group in result.product_groups:
            print(f"{group.core_name}: {group.material} {group.thickness_mm}mm x{group.quantity}")
    """
    
    def __init__(self, rules_file: Optional[Path] = None):
        """
        Inicjalizacja parsera.
        
        Args:
            rules_file: Ścieżka do pliku regex_rules.json (opcjonalna)
        """
        if rules_file:
            # Załaduj własne reguły
            from shared.parsers import name_parser
            name_parser.RULES_FILE = rules_file
            reload_rules()
    
    def get_file_type(self, extension: str) -> FileType:
        """Określ typ pliku na podstawie rozszerzenia"""
        ext_lower = extension.lower()
        return EXTENSION_MAP.get(ext_lower, FileType.OTHER)
    
    def parse_file(self, file_path: Path, root_path: Path) -> ParsedFile:
        """
        Parsuj pojedynczy plik.
        
        Args:
            file_path: Ścieżka do pliku
            root_path: Główny folder (stop dla kontekstu)
            
        Returns:
            ParsedFile z sparsowanymi danymi
        """
        extension = file_path.suffix.lower()
        file_type = self.get_file_type(extension)
        
        # Parsuj nazwę z kontekstem folderów
        parsed = parse_filename_with_folder_context(file_path, stop_at=root_path)
        
        return ParsedFile(
            path=file_path,
            filename=file_path.name,
            extension=extension,
            file_type=file_type,
            core_name=parsed.get('core_name', file_path.stem),
            material=parsed.get('material', ''),
            thickness_mm=parsed.get('thickness_mm'),
            quantity=parsed.get('quantity'),
        )
    
    def _normalize_core_name(self, name: str) -> str:
        """Normalizuj core_name dla grupowania"""
        # Usuń trailing numbers, separatory
        normalized = re.sub(r'[_\-\s]+$', '', name)
        normalized = re.sub(r'_\d+$', '', normalized)
        # Usuń suffix materiału dla lepszego grupowania (12-017118_INOX304 -> 12-017118)
        # ale zachowaj jeśli to jedyna część nazwy
        parts = normalized.split('_')
        if len(parts) > 1:
            # Sprawdź czy ostatnia część to materiał
            last = parts[-1].upper()
            material_keywords = ['INOX', 'DC01', 'S235', 'S355', 'ALU', 'ALUMINIUM', 'CORTEN', 'FE']
            for kw in material_keywords:
                if kw in last:
                    normalized = '_'.join(parts[:-1])
                    break
        return normalized.upper()
    
    def group_files(self, files: List[ParsedFile]) -> List[ProductGroup]:
        """
        Grupuj pliki w produkty.
        
        Logika:
        1. Grupuj po core_name
        2. Dla każdej grupy znajdź pliki 2D, 3D, attachments
        3. Użyj materiału/grubości z pliku 2D lub folderu
        """
        groups_dict: Dict[str, ProductGroup] = {}
        
        for pf in files:
            # Pomijaj archiwa i inne
            if pf.file_type in (FileType.ARCHIVE, FileType.OTHER):
                continue
            
            # Klucz grupowania - normalized core_name
            key = self._normalize_core_name(pf.core_name)
            
            if key not in groups_dict:
                groups_dict[key] = ProductGroup(
                    core_name=pf.core_name,
                    material=pf.material,
                    thickness_mm=pf.thickness_mm,
                    quantity=pf.quantity
                )
            
            group = groups_dict[key]
            
            # Dodaj plik do odpowiedniej listy
            if pf.file_type == FileType.FILE_2D:
                group.files_2d.append(pf)
                # Aktualizuj dane z pliku 2D (najważniejsze)
                if pf.material and not group.material:
                    group.material = pf.material
                if pf.thickness_mm and not group.thickness_mm:
                    group.thickness_mm = pf.thickness_mm
                if pf.quantity and not group.quantity:
                    group.quantity = pf.quantity
                    
            elif pf.file_type == FileType.FILE_3D:
                group.files_3d.append(pf)
                group.has_bending = True  # Zakładamy że 3D = gięcie
                
            elif pf.file_type == FileType.ATTACHMENT:
                group.attachments.append(pf)
                
            elif pf.file_type == FileType.PREVIEW:
                group.previews.append(pf)
        
        # Sortuj grupy po core_name
        groups = sorted(groups_dict.values(), key=lambda g: g.core_name)
        
        return groups
    
    def scan_folder(
        self, 
        folder_path: str | Path,
        recursive: bool = True,
        extensions: Optional[Set[str]] = None
    ) -> FolderScanResult:
        """
        Skanuj folder z plikami CAD.
        
        Args:
            folder_path: Ścieżka do folderu
            recursive: Czy skanować podkatalogi
            extensions: Opcjonalny zestaw rozszerzeń do filtrowania
            
        Returns:
            FolderScanResult z listą produktów
        """
        root_path = Path(folder_path)
        
        if not root_path.exists():
            return FolderScanResult(
                root_path=root_path,
                total_files=0,
                parsed_files=[],
                product_groups=[],
                errors=[f"Folder nie istnieje: {root_path}"]
            )
        
        if not root_path.is_dir():
            return FolderScanResult(
                root_path=root_path,
                total_files=0,
                parsed_files=[],
                product_groups=[],
                errors=[f"Ścieżka nie jest folderem: {root_path}"]
            )
        
        parsed_files: List[ParsedFile] = []
        errors: List[str] = []
        materials: Set[str] = set()
        thicknesses: Set[float] = set()
        
        # Zbierz pliki
        if recursive:
            file_paths = list(root_path.rglob('*'))
        else:
            file_paths = list(root_path.glob('*'))
        
        # Filtruj tylko pliki (nie katalogi)
        file_paths = [p for p in file_paths if p.is_file()]
        
        # Pomijaj pliki specjalne (zaczynające się od # lub zawierające NESTING)
        file_paths = [p for p in file_paths if not p.name.startswith('#') 
                      and 'NESTING' not in p.name.upper()]
        
        # Filtruj po rozszerzeniach
        if extensions:
            file_paths = [p for p in file_paths if p.suffix.lower() in extensions]
        else:
            # Domyślnie tylko znane rozszerzenia
            file_paths = [p for p in file_paths if p.suffix.lower() in EXTENSION_MAP]
        
        # Parsuj każdy plik
        for file_path in file_paths:
            try:
                pf = self.parse_file(file_path, root_path)
                parsed_files.append(pf)
                
                # Zbierz statystyki
                if pf.material:
                    materials.add(pf.material)
                if pf.thickness_mm:
                    thicknesses.add(pf.thickness_mm)
                    
            except Exception as e:
                errors.append(f"Błąd parsowania {file_path.name}: {e}")
                logger.error(f"Parse error for {file_path}: {e}")
        
        # Grupuj pliki w produkty
        product_groups = self.group_files(parsed_files)
        
        return FolderScanResult(
            root_path=root_path,
            total_files=len(file_paths),
            parsed_files=parsed_files,
            product_groups=product_groups,
            materials_found=materials,
            thicknesses_found=thicknesses,
            errors=errors
        )
    
    def scan_archive(
        self, 
        archive_path: str | Path,
        extract_to: Optional[Path] = None
    ) -> FolderScanResult:
        """
        Skanuj archiwum ZIP/7Z.
        
        Args:
            archive_path: Ścieżka do archiwum
            extract_to: Gdzie rozpakować (domyślnie: temp)
            
        Returns:
            FolderScanResult
        """
        import tempfile
        import zipfile
        
        archive_path = Path(archive_path)
        
        if not archive_path.exists():
            return FolderScanResult(
                root_path=archive_path,
                total_files=0,
                parsed_files=[],
                product_groups=[],
                errors=[f"Archiwum nie istnieje: {archive_path}"]
            )
        
        # Wypakuj do temp
        if extract_to is None:
            extract_to = Path(tempfile.mkdtemp(prefix="newerp_"))
        
        try:
            if archive_path.suffix.lower() == '.zip':
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    zf.extractall(extract_to)
            elif archive_path.suffix.lower() == '.7z':
                # Wymaga py7zr
                try:
                    import py7zr
                    with py7zr.SevenZipFile(archive_path, 'r') as zf:
                        zf.extractall(extract_to)
                except ImportError:
                    return FolderScanResult(
                        root_path=archive_path,
                        total_files=0,
                        parsed_files=[],
                        product_groups=[],
                        errors=["Brak biblioteki py7zr do obsługi archiwów 7z"]
                    )
            else:
                return FolderScanResult(
                    root_path=archive_path,
                    total_files=0,
                    parsed_files=[],
                    product_groups=[],
                    errors=[f"Nieobsługiwany format: {archive_path.suffix}"]
                )
            
            # Skanuj rozpakowany folder
            result = self.scan_folder(extract_to)
            result.root_path = archive_path  # Zachowaj oryginalną ścieżkę
            return result
            
        except Exception as e:
            return FolderScanResult(
                root_path=archive_path,
                total_files=0,
                parsed_files=[],
                product_groups=[],
                errors=[f"Błąd rozpakowywania: {e}"]
            )


# ============================================================
# Convenience Functions
# ============================================================

def scan_folder(folder_path: str | Path) -> FolderScanResult:
    """Szybkie skanowanie folderu"""
    parser = FolderParser()
    return parser.scan_folder(folder_path)


def scan_archive(archive_path: str | Path) -> FolderScanResult:
    """Szybkie skanowanie archiwum"""
    parser = FolderParser()
    return parser.scan_archive(archive_path)


# ============================================================
# CLI Test
# ============================================================

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = "/home/claude/analysis/LASERY"
    
    print(f"\n{'='*60}")
    print(f"Skanowanie: {path}")
    print('='*60)
    
    result = scan_folder(path)
    
    print(f"\n{result.summary}")
    
    print(f"\n{'='*60}")
    print("PRODUKTY:")
    print('='*60)
    
    for i, group in enumerate(result.product_groups, 1):
        print(f"\n{i}. {group.display_name}")
        print(f"   Core: {group.core_name}")
        print(f"   Ilość: {group.quantity or '?'}")
        print(f"   Gięcie: {'TAK' if group.has_bending else 'NIE'}")
        if group.primary_2d:
            print(f"   2D: {group.primary_2d.filename}")
        if group.primary_3d:
            print(f"   3D: {group.primary_3d.filename}")
        if group.primary_attachment:
            print(f"   PDF: {group.primary_attachment.filename}")
    
    if result.errors:
        print(f"\n{'='*60}")
        print("BŁĘDY:")
        for err in result.errors:
            print(f"  ⚠️ {err}")
