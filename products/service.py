#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProductService - Warstwa logiki biznesowej dla produktów

Odpowiedzialność:
- Koordynacja operacji między bazą danych a Storage
- Transakcyjność (DB + pliki jako jedna operacja)
- Generowanie miniatur
- Walidacja danych biznesowych

Zasady:
- NIGDY nie pozwól na desynchronizację DB ↔ Storage
- Kolejność przy tworzeniu: INSERT → upload plików → UPDATE ścieżki
- W przypadku błędu: partial success (produkt istnieje, ale możliwe błędy plików)

Użycie:
    from products import create_product_service
    
    service = create_product_service()
    
    # Utwórz produkt z plikami
    success, product_id = service.create_product(
        data={'name': 'Wspornik A', 'thickness_mm': 2.0},
        files={'cad_2d': dxf_bytes, 'user_image': png_bytes},
        file_extensions={'cad_2d': 'dxf', 'user_image': 'png'}
    )
"""

from typing import Optional, Dict, List, Tuple, Any
from pathlib import Path
import uuid

from products.repository import ProductRepository
from products.storage import StorageRepository
from products.paths import StoragePaths
from config.settings import (
    ALLOWED_CAD_2D, ALLOWED_CAD_3D, ALLOWED_IMAGES, ALLOWED_DOCS,
    get_mime_type, MAX_FILE_SIZE
)


class ProductService:
    """
    Serwis produktów - główny punkt wejścia dla operacji biznesowych.
    
    Koordynuje operacje między ProductRepository (DB) i StorageRepository (pliki).
    Zapewnia transakcyjność i spójność danych.
    
    Example:
        service = ProductService(product_repo, storage_repo)
        
        # Utwórz produkt
        success, result = service.create_product(
            data={'name': 'Test', 'material_id': 'xxx'},
            files={'cad_2d': bytes_data}
        )
        
        # Pobierz z URL
        product = service.get_product(product_id, include_urls=True)
    """
    
    def __init__(
        self, 
        product_repo: ProductRepository, 
        storage_repo: StorageRepository
    ):
        """
        Inicjalizacja z repozytoriami.
        
        Args:
            product_repo: Instancja ProductRepository (operacje DB)
            storage_repo: Instancja StorageRepository (operacje Storage)
        """
        self.products = product_repo
        self.storage = storage_repo
    
    # =========================================================
    # CREATE
    # =========================================================
    
    def create_product(
        self,
        data: Dict[str, Any],
        files: Dict[str, bytes] = None,
        file_extensions: Dict[str, str] = None,
        generate_thumbnails: bool = True
    ) -> Tuple[bool, str]:
        """
        Utwórz nowy produkt z plikami.
        
        Operacja transakcyjna:
        1. Walidacja danych
        2. INSERT do products_catalog → product_id
        3. Upload plików do Storage (używając product_id z bazy!)
        4. UPDATE products_catalog z ścieżkami plików
        
        W przypadku błędu uploadu: produkt pozostaje, ale bez niektórych plików.
        
        Args:
            data: Dane produktu:
                - name (wymagane): Nazwa produktu
                - material_id: UUID materiału
                - thickness_mm: Grubość w mm
                - category: Kategoria
                - description: Opis
                - notes: Uwagi
                - customer_id: UUID klienta (opcjonalne)
                - bending_cost, additional_costs, material_laser_cost: Koszty
            files: Słownik {typ: bytes}
                - cad_2d: Plik DXF/DWG
                - cad_3d: Plik STEP/STL/IGES
                - user_image: Obraz produktu
                - thumbnail_100, preview_800: Gotowe miniatury
            file_extensions: Słownik {typ: rozszerzenie}
                - np. {'cad_2d': 'dxf', 'user_image': 'png'}
            generate_thumbnails: True = generuj miniatury automatycznie
            
        Returns:
            Tuple (success: bool, product_id_or_error: str)
        """
        files = files or {}
        file_extensions = file_extensions or {}
        
        # ─────────────────────────────────────────────────────
        # KROK 0: Walidacja
        # ─────────────────────────────────────────────────────
        
        validation_error = self._validate_product_data(data, is_new=True)
        if validation_error:
            return False, validation_error
        
        for file_type, file_data in files.items():
            if file_data:
                ext = file_extensions.get(file_type, '')
                validation_error = self._validate_file(file_type, file_data, ext)
                if validation_error:
                    return False, validation_error
        
        # Generuj idx_code jeśli brak
        if not data.get('idx_code'):
            data['idx_code'] = self.products.generate_next_idx_code()
        
        # ─────────────────────────────────────────────────────
        # KROK 1: INSERT do bazy → product_id
        # ─────────────────────────────────────────────────────
        
        product_id = self.products.create(data)
        if not product_id:
            return False, "Nie udało się utworzyć produktu w bazie danych"
        
        print(f"[SERVICE] ✅ STEP 1: Product created with ID: {product_id}")
        
        # ─────────────────────────────────────────────────────
        # KROK 2: Upload plików do Storage
        # ─────────────────────────────────────────────────────
        
        uploaded_paths = {}
        file_metadata = {}  # Dodatkowe metadane plików
        upload_errors = []
        
        for file_type, file_data in files.items():
            if not file_data:
                continue
            
            ext = file_extensions.get(file_type, self._default_extension(file_type))
            path = self._get_storage_path(product_id, file_type, ext)
            
            if path:
                # Upload z automatyczną kompresją dla CAD
                success, actual_path, stats = self._upload_file(path, file_data, file_type)
                
                if success:
                    uploaded_paths[f"{file_type}_path"] = actual_path
                    
                    # Zapisz metadane pliku
                    original_filename = file_extensions.get(f"{file_type}_original_name", f"{file_type}.{ext}")
                    file_metadata[f"{file_type}_filename"] = original_filename
                    file_metadata[f"{file_type}_filesize"] = len(file_data)  # Oryginalny rozmiar
                    file_metadata[f"{file_type}_mimetype"] = get_mime_type(f"file.{ext}")
                    
                    if stats.get('is_compressed'):
                        print(f"[SERVICE] ✅ STEP 2: Uploaded {file_type} ({stats.get('compression_percent', 0):.0f}% compressed)")
                    else:
                        print(f"[SERVICE] ✅ STEP 2: Uploaded {file_type} ({len(file_data)} bytes)")
                else:
                    upload_errors.append(f"{file_type}: {actual_path}")
                    print(f"[SERVICE] ⚠️ STEP 2: Failed {file_type}: {actual_path}")
        
        # ─────────────────────────────────────────────────────
        # KROK 2b: Generowanie miniatur (opcjonalne)
        # ─────────────────────────────────────────────────────
        
        if generate_thumbnails:
            # Pobierz preferowane źródło grafiki z danych (jeśli użytkownik wybrał)
            preferred_source = data.get('primary_graphic_source')
            
            thumbnail_paths, thumb_errors = self._generate_and_upload_thumbnails(
                product_id, files, file_extensions, preferred_source
            )
            uploaded_paths.update(thumbnail_paths)
            upload_errors.extend(thumb_errors)
        
        # ─────────────────────────────────────────────────────
        # KROK 3: UPDATE ścieżki i metadane w bazie
        # ─────────────────────────────────────────────────────
        
        if uploaded_paths or file_metadata:
            # Konwertuj klucze na nazwy kolumn bazy
            db_update = {}
            
            print(f"[SERVICE] 🔍 uploaded_paths keys: {list(uploaded_paths.keys())}")
            
            for key, value in uploaded_paths.items():
                # key może być 'cad_2d_path' lub 'primary_graphic_source'
                if key.endswith('_path') or key == 'primary_graphic_source':
                    db_update[key] = value
                    print(f"[SERVICE] 📝 Adding to DB update: {key}")
            
            # Dodaj metadane plików
            for key, value in file_metadata.items():
                db_update[key] = value
            
            print(f"[SERVICE] 📋 Total DB update fields: {len(db_update)}")
            
            if db_update:
                update_success = self.products.update(product_id, db_update)
                if update_success:
                    print(f"[SERVICE] ✅ STEP 3: Updated {len(db_update)} fields in DB")
                else:
                    upload_errors.append("Nie udało się zaktualizować ścieżek w bazie")
                    print(f"[SERVICE] ❌ STEP 3: Failed to update DB")
        
        # ─────────────────────────────────────────────────────
        # PODSUMOWANIE
        # ─────────────────────────────────────────────────────
        
        if upload_errors:
            # Częściowy sukces - produkt utworzony, ale błędy przy plikach
            error_msg = "; ".join(upload_errors)
            print(f"[SERVICE] ⚠️ Product created with warnings: {error_msg}")
        else:
            print(f"[SERVICE] ✅ Product created successfully: {product_id}")
        
        # Zawsze zwracamy sukces jeśli produkt został utworzony
        return True, product_id
    
    # =========================================================
    # READ
    # =========================================================
    
    def get_product(
        self, 
        product_id: str, 
        include_urls: bool = True
    ) -> Optional[Dict]:
        """
        Pobierz produkt z opcjonalnymi URL do plików.
        
        Args:
            product_id: UUID produktu
            include_urls: True = dodaj wygenerowane URL do odpowiedzi
            
        Returns:
            Dane produktu z URL lub None
        """
        product = self.products.get_by_id(product_id)
        
        if product and include_urls:
            product = self._add_file_urls(product)
        
        return product
    
    def get_product_by_code(
        self, 
        idx_code: str, 
        include_urls: bool = True
    ) -> Optional[Dict]:
        """
        Pobierz produkt po kodzie indeksowym.
        
        Args:
            idx_code: Kod indeksowy (np. PC-202411-0001)
            include_urls: True = dodaj URL
            
        Returns:
            Dane produktu lub None
        """
        product = self.products.get_by_idx_code(idx_code)
        
        if product and include_urls:
            product = self._add_file_urls(product)
        
        return product
    
    def list_products(
        self,
        filters: Dict[str, Any] = None,
        search: str = None,
        limit: int = 50,
        offset: int = 0,
        include_urls: bool = False
    ) -> List[Dict]:
        """
        Lista produktów z filtrami.
        
        Args:
            filters: Słownik filtrów {kolumna: wartość}
            search: Tekst wyszukiwania
            limit: Limit wyników
            offset: Offset (paginacja)
            include_urls: True = dodaj URL (uwaga: wolniejsze dla dużych list!)
            
        Returns:
            Lista produktów
        """
        products = self.products.list(
            filters=filters,
            search=search,
            limit=limit,
            offset=offset
        )
        
        if include_urls:
            products = [self._add_file_urls(p) for p in products]
        
        return products
    
    def count_products(
        self,
        filters: Dict[str, Any] = None,
        search: str = None
    ) -> int:
        """Policz produkty z filtrami"""
        return self.products.count(filters=filters, search=search)
    
    # =========================================================
    # UPDATE
    # =========================================================
    
    def update_product(
        self,
        product_id: str,
        data: Dict[str, Any] = None,
        files: Dict[str, bytes] = None,
        file_extensions: Dict[str, str] = None,
        regenerate_thumbnails: bool = False
    ) -> Tuple[bool, str]:
        """
        Zaktualizuj produkt.
        
        Args:
            product_id: UUID produktu
            data: Dane do aktualizacji
            files: Nowe pliki (nadpiszą istniejące - upsert=true)
            file_extensions: Rozszerzenia plików
            regenerate_thumbnails: True = regeneruj miniatury
            
        Returns:
            Tuple (success: bool, message: str)
        """
        data = data or {}
        files = files or {}
        file_extensions = file_extensions or {}
        
        # Sprawdź czy produkt istnieje
        existing = self.products.get_by_id(product_id)
        if not existing:
            return False, f"Produkt nie istnieje: {product_id}"
        
        # Walidacja danych
        if data:
            validation_error = self._validate_product_data(data, is_new=False)
            if validation_error:
                return False, validation_error
        
        # Upload nowych plików
        uploaded_paths = {}
        errors = []
        
        for file_type, file_data in files.items():
            if not file_data:
                continue
            
            ext = file_extensions.get(file_type, self._default_extension(file_type))
            path = self._get_storage_path(product_id, file_type, ext)
            
            if path:
                success, result = self.storage.upload(path, file_data, upsert=True)
                if success:
                    uploaded_paths[f"{file_type}_path"] = result
                else:
                    errors.append(f"{file_type}: {result}")
        
        # Regeneruj miniatury jeśli potrzeba
        if regenerate_thumbnails or files:
            # Użyj nowych plików lub pobierz istniejące
            all_files = files.copy()
            
            # Pobierz preferowane źródło grafiki z danych
            preferred_source = data.get('primary_graphic_source')
            
            thumb_paths, thumb_errors = self._generate_and_upload_thumbnails(
                product_id, all_files, file_extensions, preferred_source
            )
            uploaded_paths.update(thumb_paths)
            errors.extend(thumb_errors)
        
        # Zaktualizuj bazę
        update_data = {**data, **uploaded_paths}
        if update_data:
            success = self.products.update(product_id, update_data)
            if not success:
                return False, "Nie udało się zaktualizować produktu w bazie"
        
        if errors:
            return True, f"Zaktualizowano z ostrzeżeniami: {'; '.join(errors)}"
        
        return True, "Produkt zaktualizowany"
    
    # =========================================================
    # DELETE
    # =========================================================
    
    def delete_product(
        self, 
        product_id: str, 
        hard: bool = False
    ) -> Tuple[bool, str]:
        """
        Usuń produkt.
        
        Args:
            product_id: UUID produktu
            hard: True = trwałe usunięcie (z plikami), False = soft delete
            
        Returns:
            Tuple (success: bool, message: str)
        """
        # Sprawdź czy produkt istnieje
        existing = self.products.get_by_id(product_id)
        if not existing:
            return False, f"Produkt nie istnieje: {product_id}"
        
        if hard:
            # Usuń pliki ze Storage
            deleted_files = self.storage.delete_product_files(product_id)
            print(f"[SERVICE] Deleted {deleted_files} files from Storage")
        
        # Usuń z bazy
        success = self.products.delete(product_id, hard=hard)
        
        if success:
            action = "trwale usunięty" if hard else "oznaczony jako usunięty"
            return True, f"Produkt {action}"
        else:
            return False, "Nie udało się usunąć produktu"
    
    def restore_product(self, product_id: str) -> Tuple[bool, str]:
        """Przywróć usunięty produkt (soft delete)"""
        success = self.products.restore(product_id)
        if success:
            return True, "Produkt przywrócony"
        return False, "Nie udało się przywrócić produktu"
    
    # =========================================================
    # ATTACHMENTS
    # =========================================================
    
    def add_attachment(
        self,
        product_id: str,
        file_data: bytes,
        filename: str,
        note: str = None
    ) -> Tuple[bool, str]:
        """
        Dodaj załącznik do produktu.
        
        Args:
            product_id: UUID produktu
            file_data: Dane pliku
            filename: Oryginalna nazwa pliku
            note: Opcjonalna notatka
            
        Returns:
            Tuple (success: bool, attachment_id_or_error: str)
        """
        # Sprawdź czy produkt istnieje
        if not self.products.get_by_id(product_id):
            return False, f"Produkt nie istnieje: {product_id}"
        
        # Walidacja rozmiaru
        if len(file_data) > MAX_FILE_SIZE:
            return False, "Plik za duży"
        
        # Generuj ID załącznika
        attachment_id = str(uuid.uuid4())
        
        # Ścieżka w Storage
        storage_path = StoragePaths.attachment(product_id, attachment_id, filename)
        
        # Upload pliku (upsert=false - załączniki są unikalne)
        success, result = self.storage.upload(storage_path, file_data, upsert=False)
        
        if not success:
            return False, f"Nie udało się uploadować pliku: {result}"
        
        # Utwórz rekord w bazie
        attachment_data = {
            'id': attachment_id,
            'product_id': product_id,
            'original_filename': filename,
            'storage_path': storage_path,
            'filesize': len(file_data),
            'mimetype': get_mime_type(filename),
            'note': note,
        }
        
        created_id = self.products.create_attachment(attachment_data)
        
        if created_id:
            return True, created_id
        else:
            # Rollback - usuń plik
            self.storage.delete(storage_path)
            return False, "Nie udało się utworzyć rekordu załącznika"
    
    def get_attachments(
        self, 
        product_id: str, 
        include_urls: bool = True
    ) -> List[Dict]:
        """
        Pobierz załączniki produktu z URL.
        
        Args:
            product_id: UUID produktu
            include_urls: True = dodaj signed URLs
            
        Returns:
            Lista załączników
        """
        attachments = self.products.get_attachments(product_id)
        
        if include_urls:
            for att in attachments:
                if att.get('storage_path'):
                    att['signed_url'] = self.storage.get_signed_url(att['storage_path'])
                    att['public_url'] = self.storage.get_public_url(att['storage_path'])
        
        return attachments
    
    def delete_attachment(
        self, 
        attachment_id: str,
        hard: bool = True
    ) -> Tuple[bool, str]:
        """
        Usuń załącznik.
        
        Args:
            attachment_id: UUID załącznika
            hard: True = usuń też plik ze Storage
            
        Returns:
            Tuple (success: bool, message: str)
        """
        # Pobierz info o załączniku
        attachment = self.products.get_attachment(attachment_id)
        if not attachment:
            return False, "Załącznik nie istnieje"
        
        # Usuń plik ze Storage
        if hard and attachment.get('storage_path'):
            self.storage.delete(attachment['storage_path'])
        
        # Usuń z bazy
        success = self.products.delete_attachment(attachment_id, hard=hard)
        
        if success:
            return True, "Załącznik usunięty"
        return False, "Nie udało się usunąć załącznika"
    
    # =========================================================
    # FILE DOWNLOAD
    # =========================================================
    
    def download_file(
        self, 
        product_id: str, 
        file_type: str
    ) -> Tuple[bool, bytes, str]:
        """
        Pobierz plik produktu (z automatyczną dekompresją).
        
        Args:
            product_id: UUID produktu
            file_type: Typ pliku ('cad_2d', 'cad_3d', 'user_image', etc.)
            
        Returns:
            Tuple (success, data, filename)
        """
        product = self.products.get_by_id(product_id)
        if not product:
            return False, b"", "Produkt nie istnieje"
        
        # Pobierz ścieżkę
        path_key = f"{file_type}_path"
        path = product.get(path_key)
        
        if not path:
            return False, b"", f"Brak pliku typu {file_type}"
        
        # Pobierz dane z automatyczną dekompresją
        # Usuń .gz z path jeśli zapisana jest wersja skompresowana
        base_path = path[:-3] if path.endswith('.gz') else path
        success, data, stats = self._download_file(base_path, file_type)
        
        if success:
            filename = product.get(f"{file_type}_filename") or Path(base_path).name
            return True, data, filename
        
        return False, b"", "Nie udało się pobrać pliku"
    
    # =========================================================
    # HELPERS - Walidacja
    # =========================================================
    
    def _validate_product_data(
        self, 
        data: Dict, 
        is_new: bool
    ) -> Optional[str]:
        """
        Waliduj dane produktu.
        
        Returns:
            None jeśli OK, komunikat błędu w przeciwnym razie
        """
        if is_new:
            if not data.get('name'):
                return "Nazwa produktu jest wymagana"
            if not data.get('name').strip():
                return "Nazwa produktu nie może być pusta"
        
        # Walidacja thickness_mm
        if 'thickness_mm' in data and data['thickness_mm'] is not None:
            try:
                thickness = float(data['thickness_mm'])
                if thickness <= 0:
                    return "Grubość musi być większa od 0"
                if thickness > 1000:
                    return "Grubość nie może przekraczać 1000 mm"
            except (TypeError, ValueError):
                return "Nieprawidłowa wartość grubości"
        
        # Walidacja kosztów
        for cost_field in ['bending_cost', 'additional_costs', 'material_laser_cost', 
                          'material_cost', 'laser_cost']:
            if cost_field in data and data[cost_field] is not None:
                try:
                    cost = float(data[cost_field])
                    if cost < 0:
                        return f"{cost_field} nie może być ujemny"
                except (TypeError, ValueError):
                    return f"Nieprawidłowa wartość {cost_field}"
        
        return None
    
    def _validate_file(
        self, 
        file_type: str, 
        data: bytes, 
        extension: str
    ) -> Optional[str]:
        """
        Waliduj plik.
        
        Returns:
            None jeśli OK, komunikat błędu w przeciwnym razie
        """
        # Walidacja rozmiaru
        if len(data) > MAX_FILE_SIZE:
            size_mb = len(data) / (1024 * 1024)
            max_mb = MAX_FILE_SIZE / (1024 * 1024)
            return f"Plik {file_type} za duży ({size_mb:.1f} MB > {max_mb:.0f} MB)"
        
        # Walidacja rozszerzenia
        ext = f".{extension.lstrip('.')}" if extension else ""
        
        type_extensions = {
            'cad_2d': ALLOWED_CAD_2D,
            'cad_3d': ALLOWED_CAD_3D,
            'user_image': ALLOWED_IMAGES,
            'documentation': ALLOWED_DOCS,
        }
        
        allowed = type_extensions.get(file_type)
        if allowed and ext and ext.lower() not in allowed:
            return f"Niedozwolone rozszerzenie {ext} dla {file_type}. Dozwolone: {allowed}"
        
        return None
    
    # =========================================================
    # HELPERS - Ścieżki i rozszerzenia
    # =========================================================
    
    def _default_extension(self, file_type: str) -> str:
        """Zwróć domyślne rozszerzenie dla typu pliku"""
        defaults = {
            'cad_2d': 'dxf',
            'cad_3d': 'step',
            'user_image': 'png',
            'thumbnail_100': 'png',
            'preview_800': 'png',
            'documentation': 'zip',
        }
        return defaults.get(file_type, '')
    
    def _get_size_from_name(self, thumb_name: str) -> int:
        """Pobierz rozmiar z nazwy miniatury"""
        size_map = {
            'thumbnail_100': 100,
            'preview_800': 800,
        }
        return size_map.get(thumb_name, 100)
    
    def _get_storage_path(
        self, 
        product_id: str, 
        file_type: str, 
        extension: str
    ) -> Optional[str]:
        """Generuj ścieżkę Storage dla typu pliku"""
        
        path_methods = {
            'cad_2d': lambda: StoragePaths.cad_2d(product_id, extension),
            'cad_3d': lambda: StoragePaths.cad_3d(product_id, extension),
            'user_image': lambda: StoragePaths.user_image(product_id, extension),
            'thumbnail_100': lambda: StoragePaths.thumbnail_100(product_id),
            'preview_800': lambda: StoragePaths.preview_800(product_id),
        }
        
        method = path_methods.get(file_type)
        if method:
            return method()
        
        return None
    
    def _upload_file(
        self,
        path: str,
        data: bytes,
        file_type: str,
        use_compression: bool = True
    ) -> Tuple[bool, str, Dict]:
        """
        Upload pliku z opcjonalną kompresją.
        
        Kompresja jest stosowana dla plików CAD (cad_2d, cad_3d)
        i obrazów źródłowych, ale NIE dla miniatur.
        
        Args:
            path: Ścieżka docelowa
            data: Dane pliku
            file_type: Typ pliku (cad_2d, cad_3d, user_image, etc.)
            use_compression: Czy używać kompresji
            
        Returns:
            Tuple (success, actual_path, stats)
        """
        # Kompresja tylko dla CAD i user_image (nie dla miniatur)
        compress_types = {'cad_2d', 'cad_3d', 'user_image'}
        should_compress = use_compression and file_type in compress_types
        
        if should_compress:
            success, actual_path, stats = self.storage.upload_compressed(path, data)
            return success, actual_path if success else path, stats
        else:
            success, result = self.storage.upload(path, data, upsert=True)
            return success, result, {'is_compressed': False, 'original_size': len(data)}
    
    def _download_file(
        self,
        path: str,
        file_type: str
    ) -> Tuple[bool, bytes, Dict]:
        """
        Pobierz plik z automatyczną dekompresją.
        
        Args:
            path: Ścieżka pliku (bez .gz)
            file_type: Typ pliku
            
        Returns:
            Tuple (success, data, stats)
        """
        # Typy które mogą być skompresowane
        compress_types = {'cad_2d', 'cad_3d', 'user_image'}
        
        if file_type in compress_types:
            return self.storage.download_decompressed(path)
        else:
            success, data = self.storage.download(path)
            return success, data, {'was_compressed': False}
    
    # =========================================================
    # HELPERS - URL
    # =========================================================
    
    def _add_file_urls(self, product: Dict) -> Dict:
        """Dodaj URL do ścieżek plików produktu"""
        
        path_columns = [
            'cad_2d_path', 'cad_3d_path', 'user_image_path',
            'thumbnail_100_path', 'preview_800_path',
            'additional_documentation_path'
        ]
        
        for col in path_columns:
            path = product.get(col)
            if path:
                url = self.storage.get_signed_url(path)
                if url:
                    url_col = col.replace('_path', '_url')
                    product[url_col] = url
        
        return product
    
    # =========================================================
    # HELPERS - Miniatury
    # =========================================================
    
    def _generate_and_upload_thumbnails(
        self,
        product_id: str,
        files: Dict[str, bytes],
        extensions: Dict[str, str],
        preferred_source: str = None
    ) -> Tuple[Dict[str, str], List[str]]:
        """
        Generuj i uploaduj miniatury z WSZYSTKICH dostępnych źródeł.
        
        Miniatury są zapisywane w oddzielnych folderach:
        - previews_2d/ - z pliku DXF
        - previews_3d/ - z pliku STEP/IGES
        - previews_user/ - z obrazu użytkownika
        - previews/ - główna miniatura (kopia z primary_graphic_source)
        
        Args:
            product_id: UUID produktu
            files: Słownik plików źródłowych
            extensions: Słownik rozszerzeń
            preferred_source: Ręcznie wybrany źródło ('USER', '2D', '3D' lub None = auto)
            
        Returns:
            Tuple (uploaded_paths: Dict, errors: List)
        """
        uploaded_paths = {}
        errors = []
        
        # Mapowanie źródeł
        source_configs = [
            ('user_image', 'USER', 'user'),
            ('cad_2d', '2D', '2d'),
            ('cad_3d', '3D', '3d'),
        ]
        
        # Kolejność priorytetów dla primary_graphic_source
        # Jeśli użytkownik wybrał źródło, użyj tego jako pierwszego w priorytecie
        # Domyślny priorytet: USER > 3D > 2D (3D jest lepsze niż płaski DXF)
        if preferred_source in ['USER', '2D', '3D']:
            priority_order = [preferred_source] + [s for s in ['USER', '3D', '2D'] if s != preferred_source]
            print(f"[SERVICE] 📌 User selected primary source: {preferred_source}")
        else:
            priority_order = ['USER', '3D', '2D']
        
        generated_sources = []
        
        try:
            from products.utils.thumbnail_generator import ThumbnailGenerator
            generator = ThumbnailGenerator()
            
            # Generuj miniatury z KAŻDEGO dostępnego źródła
            for file_key, source_type, folder_suffix in source_configs:
                file_data = files.get(file_key)
                if not file_data:
                    continue
                
                ext = extensions.get(file_key, 'png')
                print(f"[SERVICE] 📷 Generating thumbnails from {source_type} ({ext})...")
                
                thumbnails = generator.generate(file_data, ext)
                
                if thumbnails:
                    print(f"[SERVICE] ✅ Generated {len(thumbnails)} thumbnails from {source_type}")
                    generated_sources.append(source_type)
                    
                    # Upload do folderu źródłowego (np. previews_2d/)
                    for thumb_name, thumb_data in thumbnails.items():
                        # Ścieżka z suffixem źródła
                        thumb_path = StoragePaths.thumbnail(
                            product_id, 
                            self._get_size_from_name(thumb_name),
                            source=folder_suffix
                        )
                        
                        success, result = self.storage.upload(
                            thumb_path, thumb_data,
                            content_type='image/png', upsert=True
                        )
                        
                        if success:
                            # NIE zapisujemy ścieżek źródłowych do DB 
                            # (tylko do storage - mogą być potrzebne w przyszłości)
                            # Ścieżki są deterministyczne więc można je odtworzyć
                            print(f"[SERVICE] ✅ Uploaded {thumb_name} ({source_type})")
                        else:
                            errors.append(f"Thumbnail {thumb_name} ({source_type}): {result}")
                else:
                    print(f"[SERVICE] ⚠️ No thumbnails generated from {source_type}")
            
            # Ustaw primary_graphic_source według priorytetu
            primary_source = None
            for src in priority_order:
                if src in generated_sources:
                    primary_source = src
                    break
            
            if primary_source:
                uploaded_paths['primary_graphic_source'] = primary_source
                
                # Kopiuj miniatury z primary source do głównego folderu (previews/)
                folder_map = {'USER': 'user', '2D': '2d', '3D': '3d'}
                primary_folder = folder_map[primary_source]
                
                for thumb_name in ['thumbnail_100', 'preview_800']:
                    source_path = StoragePaths.thumbnail(
                        product_id,
                        self._get_size_from_name(thumb_name),
                        source=primary_folder
                    )
                    
                    success, data = self.storage.download(source_path)
                    if success:
                        main_path = StoragePaths.thumbnail(
                            product_id,
                            self._get_size_from_name(thumb_name)
                        )
                        upload_ok, result = self.storage.upload(
                            main_path, data,
                            content_type='image/png', upsert=True
                        )
                        if upload_ok:
                            uploaded_paths[f'{thumb_name}_path'] = result
                
                print(f"[SERVICE] ✅ Main thumbnails set from {primary_source}")
                
        except ImportError as e:
            print(f"[SERVICE] ⚠️ ThumbnailGenerator import error: {e}")
            errors.append(f"Brak biblioteki do generowania miniatur")
        except Exception as e:
            print(f"[SERVICE] ⚠️ Thumbnail generation error: {e}")
            import traceback
            traceback.print_exc()
            errors.append(f"Błąd generowania miniatur: {e}")
        
        return uploaded_paths, errors


# =========================================================
# FACTORY
# =========================================================

def create_product_service(client=None) -> ProductService:
    """
    Factory method do tworzenia ProductService.
    
    Tworzy wszystkie wymagane zależności (repozytoria).
    
    Args:
        client: Opcjonalna instancja Supabase Client
                (jeśli None - użyje get_supabase_client())
        
    Returns:
        Skonfigurowana instancja ProductService
        
    Example:
        from products import create_product_service
        
        service = create_product_service()
        products = service.list_products()
    """
    if client is None:
        from core.supabase_client import get_supabase_client
        client = get_supabase_client()
    
    product_repo = ProductRepository(client)
    storage_repo = StorageRepository(client)
    
    return ProductService(product_repo, storage_repo)


# =========================================================
# TESTY
# =========================================================

if __name__ == "__main__":
    print("ProductService - warstwa logiki biznesowej")
    print("Użyj: service = create_product_service()")
    print()
    print("Przykład:")
    print("  success, result = service.create_product({'name': 'Test'})")
    print("  product = service.get_product(result)")
