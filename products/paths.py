#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StoragePaths - Deterministyczne ścieżki plików w Supabase Storage

Zasady:
1. Pliki "główne" (CAD, obrazy, miniatury) mają STAŁE nazwy → upsert=true
2. Załączniki mają strukturę {attachment_id}/{original_filename} → bezkolizyjne
3. Wszystkie ścieżki są generowane z product_id → pełna spójność

Struktura w Storage:
    products/{product_id}/
    ├── cad/
    │   ├── 2d/cad_2d.{ext}          ← STAŁA NAZWA
    │   └── 3d/cad_3d.{ext}          ← STAŁA NAZWA
    ├── images/
    │   ├── source/user_image.{ext}  ← STAŁA NAZWA
    │   └── previews/
    │       ├── thumbnail_100.png    ← STAŁA NAZWA
    │       └── preview_800.png      ← STAŁA NAZWA
    └── attachments/
        └── {attachment_id}/
            └── {original_filename}   ← UNIKALNY per attachment_id
"""

from pathlib import Path
from typing import Optional, Dict

from config.settings import STORAGE_BUCKET, STORAGE_BASE_PATH, SUPABASE_URL


class StoragePaths:
    """
    Generator deterministycznych ścieżek w Supabase Storage.
    
    Wszystkie metody są statyczne - nie wymagają instancji klasy.
    
    Przykład użycia:
        path = StoragePaths.cad_2d("abc-123-def", "dxf")
        # → "products/abc-123-def/cad/2d/cad_2d.dxf"
        
        url = StoragePaths.get_public_url(path)
        # → "https://xxx.supabase.co/storage/v1/object/public/product_files/products/abc-123-def/cad/2d/cad_2d.dxf"
    """
    
    BUCKET = STORAGE_BUCKET
    BASE = STORAGE_BASE_PATH
    
    # =========================================================
    # PLIKI CAD
    # =========================================================
    
    @staticmethod
    def cad_2d(product_id: str, extension: str = "dxf") -> str:
        """
        Ścieżka do pliku CAD 2D (DXF/DWG).
        
        Args:
            product_id: UUID produktu
            extension: Rozszerzenie pliku (bez kropki)
            
        Returns:
            Ścieżka: products/{id}/cad/2d/cad_2d.{ext}
        """
        ext = extension.lstrip('.')
        return f"{StoragePaths.BASE}/{product_id}/cad/2d/cad_2d.{ext}"
    
    @staticmethod
    def cad_3d(product_id: str, extension: str = "step") -> str:
        """
        Ścieżka do pliku CAD 3D (STEP/STL/IGES).
        
        Args:
            product_id: UUID produktu
            extension: Rozszerzenie pliku (bez kropki)
            
        Returns:
            Ścieżka: products/{id}/cad/3d/cad_3d.{ext}
        """
        ext = extension.lstrip('.')
        return f"{StoragePaths.BASE}/{product_id}/cad/3d/cad_3d.{ext}"
    
    # =========================================================
    # OBRAZY I MINIATURY
    # =========================================================
    
    @staticmethod
    def user_image(product_id: str, extension: str = "png") -> str:
        """
        Ścieżka do obrazu użytkownika (źródłowego).
        
        Args:
            product_id: UUID produktu
            extension: Rozszerzenie pliku (bez kropki)
            
        Returns:
            Ścieżka: products/{id}/images/source/user_image.{ext}
        """
        ext = extension.lstrip('.')
        return f"{StoragePaths.BASE}/{product_id}/images/source/user_image.{ext}"
    
    @staticmethod
    def thumbnail(product_id: str, size: int = 100, source: str = None) -> str:
        """
        Ścieżka do miniatury/podglądu (zawsze PNG).
        
        Args:
            product_id: UUID produktu
            size: Rozmiar w pikselach (100, 800, 4096)
            source: Źródło miniatury ('2d', '3d', 'user' lub None dla głównego)
            
        Returns:
            Ścieżka do pliku PNG z miniaturą
        """
        size_names = {
            100: "thumbnail_100",
            800: "preview_800",
            4096: "preview_4k",
            3840: "preview_4k",  # alias dla 4K
        }
        name = size_names.get(size, f"preview_{size}")
        
        # Jeśli podano źródło, użyj oddzielnego folderu
        if source:
            source = source.lower()
            if source in ('2d', '3d', 'user'):
                return f"{StoragePaths.BASE}/{product_id}/images/previews_{source}/{name}.png"
        
        # Domyślna ścieżka (główna miniatura)
        return f"{StoragePaths.BASE}/{product_id}/images/previews/{name}.png"
    
    @staticmethod
    def thumbnail_2d(product_id: str, size: int = 100) -> str:
        """Miniatura z pliku 2D (DXF)"""
        return StoragePaths.thumbnail(product_id, size, source='2d')
    
    @staticmethod
    def thumbnail_3d(product_id: str, size: int = 100) -> str:
        """Miniatura z pliku 3D (STEP/IGES)"""
        return StoragePaths.thumbnail(product_id, size, source='3d')
    
    @staticmethod
    def thumbnail_user(product_id: str, size: int = 100) -> str:
        """Miniatura z obrazu użytkownika"""
        return StoragePaths.thumbnail(product_id, size, source='user')
    
    @staticmethod
    def thumbnail_100(product_id: str) -> str:
        """Skrót do miniatury 100x100px"""
        return StoragePaths.thumbnail(product_id, 100)
    
    @staticmethod
    def preview_800(product_id: str) -> str:
        """Skrót do podglądu 800x800px"""
        return StoragePaths.thumbnail(product_id, 800)
    
    @staticmethod
    def preview_4k(product_id: str) -> str:
        """Skrót do podglądu 4K (4096px)"""
        return StoragePaths.thumbnail(product_id, 4096)
    
    # =========================================================
    # ZAŁĄCZNIKI
    # =========================================================
    
    @staticmethod
    def attachment(product_id: str, attachment_id: str, filename: str) -> str:
        """
        Ścieżka do załącznika produktu.
        
        Załączniki są przechowywane z oryginalną nazwą pliku w folderze
        o nazwie attachment_id, co zapewnia unikalność nawet przy
        identycznych nazwach plików.
        
        Args:
            product_id: UUID produktu
            attachment_id: UUID załącznika (z tabeli product_attachments)
            filename: Oryginalna nazwa pliku
            
        Returns:
            Ścieżka: products/{id}/attachments/{attachment_id}/{filename}
        """
        # Zabezpiecz nazwę pliku - usuń ścieżkę, zostaw tylko nazwę
        safe_filename = Path(filename).name
        return f"{StoragePaths.BASE}/{product_id}/attachments/{attachment_id}/{safe_filename}"
    
    @staticmethod
    def documentation(product_id: str, extension: str = "zip") -> str:
        """
        Ścieżka do głównej dokumentacji (dla kompatybilności).
        
        UWAGA: W nowej architekturze dokumentacja powinna być załącznikiem
        w tabeli product_attachments. Ta metoda jest dla kompatybilności
        ze starym kodem.
        
        Args:
            product_id: UUID produktu
            extension: Rozszerzenie pliku
            
        Returns:
            Ścieżka: products/{id}/documentation/main.{ext}
        """
        ext = extension.lstrip('.')
        return f"{StoragePaths.BASE}/{product_id}/documentation/main.{ext}"
    
    # =========================================================
    # GENEROWANIE URL
    # =========================================================
    
    @staticmethod
    def get_public_url(path: str) -> str:
        """
        Generuj publiczny URL ze ścieżki Storage.
        
        UWAGA: Wymaga publicznego bucketa lub publicznej polityki RLS!
        
        Args:
            path: Ścieżka w Storage (np. "products/abc/cad/2d/cad_2d.dxf")
            
        Returns:
            Pełny URL publiczny
            
        Example:
            >>> StoragePaths.get_public_url("products/abc/cad/2d/cad_2d.dxf")
            "https://xxx.supabase.co/storage/v1/object/public/product_files/products/abc/cad/2d/cad_2d.dxf"
        """
        if not path:
            return ""
        return f"{SUPABASE_URL}/storage/v1/object/public/{StoragePaths.BUCKET}/{path}"
    
    @staticmethod
    def get_signed_url(client, path: str, expires_in: int = 86400) -> Optional[str]:
        """
        Generuj podpisany URL ze ścieżki Storage.
        
        Używaj dla plików niepublicznych lub gdy potrzebujesz
        tymczasowego dostępu.
        
        Args:
            client: Instancja Supabase Client
            path: Ścieżka w Storage
            expires_in: Czas ważności w sekundach (domyślnie 24h)
            
        Returns:
            Podpisany URL lub None w przypadku błędu
        """
        if not path:
            return None
        
        try:
            response = client.storage.from_(StoragePaths.BUCKET).create_signed_url(
                path, expires_in
            )
            return response.get('signedURL')
        except Exception as e:
            print(f"[ERROR] Nie można wygenerować signed URL dla {path}: {e}")
            return None
    
    # =========================================================
    # EKSTRAKCJA I PARSOWANIE
    # =========================================================
    
    @staticmethod
    def extract_path_from_url(url: str) -> Optional[str]:
        """
        Wyciągnij ścieżkę Storage z pełnego URL.
        
        Args:
            url: Pełny URL do pliku w Storage
            
        Returns:
            Ścieżka w Storage lub None
            
        Example:
            >>> url = "https://xxx.supabase.co/storage/v1/object/public/product_files/products/abc/file.dxf"
            >>> StoragePaths.extract_path_from_url(url)
            "products/abc/file.dxf"
        """
        if not url:
            return None
        
        # Pattern dla public URL
        marker = f"/storage/v1/object/public/{StoragePaths.BUCKET}/"
        if marker in url:
            return url.split(marker)[1].split('?')[0]  # Usuń query params
        
        # Pattern dla signed URL
        marker_signed = f"/storage/v1/object/sign/{StoragePaths.BUCKET}/"
        if marker_signed in url:
            return url.split(marker_signed)[1].split('?')[0]
        
        return None
    
    @staticmethod
    def get_extension_from_filename(filename: str) -> str:
        """
        Wyciągnij rozszerzenie z nazwy pliku (bez kropki, lowercase).
        
        Args:
            filename: Nazwa pliku
            
        Returns:
            Rozszerzenie bez kropki (np. "dxf", "step")
        """
        return Path(filename).suffix.lstrip('.').lower()
    
    @staticmethod
    def get_extension_from_path(path: str) -> str:
        """
        Wyciągnij rozszerzenie ze ścieżki Storage.
        
        Args:
            path: Ścieżka w Storage
            
        Returns:
            Rozszerzenie bez kropki
        """
        return StoragePaths.get_extension_from_filename(path)
    
    # =========================================================
    # POMOCNICZE
    # =========================================================
    
    @staticmethod
    def product_folder(product_id: str) -> str:
        """
        Ścieżka do głównego folderu produktu.
        
        Przydatne do listowania wszystkich plików produktu
        lub usuwania całego produktu.
        
        Args:
            product_id: UUID produktu
            
        Returns:
            Ścieżka: products/{product_id}
        """
        return f"{StoragePaths.BASE}/{product_id}"
    
    @staticmethod
    def list_all_paths_for_product(product_id: str) -> Dict[str, str]:
        """
        Zwróć słownik wszystkich możliwych ścieżek dla produktu.
        
        Przydatne do debugowania i weryfikacji struktury.
        
        Args:
            product_id: UUID produktu
            
        Returns:
            Słownik {nazwa: ścieżka}
        """
        return {
            'product_folder': StoragePaths.product_folder(product_id),
            'cad_2d': StoragePaths.cad_2d(product_id),
            'cad_3d': StoragePaths.cad_3d(product_id),
            'user_image': StoragePaths.user_image(product_id),
            'thumbnail_100': StoragePaths.thumbnail_100(product_id),
            'preview_800': StoragePaths.preview_800(product_id),
            'attachments_folder': f"{StoragePaths.BASE}/{product_id}/attachments/",
        }
    
    @staticmethod
    def get_file_type_from_path(path: str) -> Optional[str]:
        """
        Określ typ pliku na podstawie ścieżki Storage.
        
        Args:
            path: Ścieżka w Storage
            
        Returns:
            Typ pliku: 'cad_2d', 'cad_3d', 'user_image', 'thumbnail', 'attachment' lub None
        """
        if not path:
            return None
        
        if '/cad/2d/' in path:
            return 'cad_2d'
        elif '/cad/3d/' in path:
            return 'cad_3d'
        elif '/images/source/' in path:
            return 'user_image'
        elif '/images/previews/' in path:
            return 'thumbnail'
        elif '/attachments/' in path:
            return 'attachment'
        elif '/documentation/' in path:
            return 'documentation'
        
        return None


# =========================================================
# TESTY
# =========================================================

if __name__ == "__main__":
    # Test generowania ścieżek
    test_product_id = "3f8ee668-372a-4fa5-b75d-00ca0f9b3716"
    test_attachment_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    
    print("=" * 70)
    print("TEST STORAGE PATHS")
    print("=" * 70)
    
    print(f"\n📁 Product ID: {test_product_id}")
    print()
    
    paths = StoragePaths.list_all_paths_for_product(test_product_id)
    for name, path in paths.items():
        print(f"  {name:20} → {path}")
    
    print(f"\n📎 Załącznik ID: {test_attachment_id}")
    attachment_path = StoragePaths.attachment(
        test_product_id, 
        test_attachment_id, 
        "dokumentacja_techniczna.pdf"
    )
    print(f"  attachment → {attachment_path}")
    
    print(f"\n🔗 URL publiczny (thumbnail_100):")
    print(f"  {StoragePaths.get_public_url(paths['thumbnail_100'])}")
    
    print(f"\n🔍 Ekstrakcja ścieżki z URL:")
    test_url = StoragePaths.get_public_url(paths['cad_2d'])
    extracted = StoragePaths.extract_path_from_url(test_url)
    print(f"  URL: {test_url}")
    print(f"  Ścieżka: {extracted}")
    
    print(f"\n📂 Typ pliku ze ścieżki:")
    for name, path in list(paths.items())[:4]:
        file_type = StoragePaths.get_file_type_from_path(path)
        print(f"  {path} → {file_type}")
    
    print("\n" + "=" * 70)
    print("✅ Test zakończony")
    print("=" * 70)
