#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StorageRepository - Warstwa dostępu do Supabase Storage

Odpowiedzialność:
- Upload/download plików
- Generowanie URL (publicznych i podpisanych)
- Zarządzanie plikami (usuwanie, listowanie)
- Cache URL dla wydajności

Zasady:
- Używa SERVICE_ROLE_KEY (pełne uprawnienia)
- Wszystkie metody są atomowe
- Obsługuje błędy gracefully (zwraca tuple success/error)
"""

import os
from typing import Optional, List, Dict, Tuple
from pathlib import Path
from datetime import datetime, timedelta

from supabase import Client

from config.settings import (
    STORAGE_BUCKET, 
    MAX_FILE_SIZE, 
    get_mime_type,
    URL_CACHE_TTL,
    COMPRESSION_STRATEGY,
    COMPRESSION_LEVEL
)
from products.paths import StoragePaths
from products.utils.compression import (
    CompressionManager, 
    CompressionStrategy,
    create_compression_manager
)


class StorageRepository:
    """
    Repository dla operacji na Supabase Storage.
    
    Użyj tej klasy zamiast bezpośrednich operacji na client.storage.
    Zapewnia:
    - Spójne logowanie
    - Obsługę błędów
    - Cache URL
    - Walidację rozmiaru plików
    
    Example:
        from core import get_supabase_client
        from products.storage import StorageRepository
        
        client = get_supabase_client()
        storage = StorageRepository(client)
        
        # Upload
        success, result = storage.upload("path/to/file.dxf", file_bytes)
        
        # Download
        success, data = storage.download("path/to/file.dxf")
    """
    
    def __init__(self, client: Client, compression_strategy: str = None):
        """
        Inicjalizacja z klientem Supabase.
        
        Args:
            client: Instancja Supabase Client (z SERVICE_ROLE_KEY)
            compression_strategy: Strategia kompresji (none/individual/bundle/hybrid)
        """
        self.client = client
        self.bucket = STORAGE_BUCKET
        
        # Cache dla signed URLs - {path: (url, timestamp)}
        self._url_cache: Dict[str, Tuple[str, datetime]] = {}
        
        # Manager kompresji
        strategy = compression_strategy or COMPRESSION_STRATEGY
        self.compression = create_compression_manager(strategy)
        self.compression.compression_level = COMPRESSION_LEVEL
    
    # =========================================================
    # UPLOAD
    # =========================================================
    
    def upload(
        self, 
        path: str, 
        data: bytes, 
        content_type: Optional[str] = None,
        upsert: bool = True
    ) -> Tuple[bool, str]:
        """
        Upload pliku do Storage.
        
        Args:
            path: Ścieżka docelowa w Storage (np. z StoragePaths)
            data: Dane binarne pliku
            content_type: MIME type (auto-detect jeśli None)
            upsert: True = nadpisz jeśli plik istnieje
            
        Returns:
            Tuple (success: bool, path_or_error: str)
            - success=True: zwraca ścieżkę pliku
            - success=False: zwraca komunikat błędu
        """
        if not path:
            return False, "Brak ścieżki docelowej"
        
        if not data:
            return False, "Brak danych do uploadu"
        
        # Walidacja rozmiaru
        if len(data) > MAX_FILE_SIZE:
            size_mb = len(data) / (1024 * 1024)
            max_mb = MAX_FILE_SIZE / (1024 * 1024)
            return False, f"Plik za duży ({size_mb:.1f} MB > {max_mb:.0f} MB)"
        
        # Auto-detect MIME type
        if not content_type:
            content_type = get_mime_type(path)
        
        try:
            # Upload z upsert jako STRING (wymagane przez Supabase!)
            self.client.storage.from_(self.bucket).upload(
                path=path,
                file=data,
                file_options={
                    "content-type": content_type,
                    "upsert": "true" if upsert else "false"
                }
            )
            
            print(f"[STORAGE] ✅ Upload: {path} ({len(data):,} bytes)")
            return True, path
            
        except Exception as e:
            error_msg = str(e)
            
            # Obsługa duplikatu gdy upsert=false
            if "Duplicate" in error_msg and not upsert:
                print(f"[STORAGE] ⚠️ Plik już istnieje: {path}")
                return False, "Plik już istnieje"
            
            print(f"[STORAGE] ❌ Upload failed: {path} - {error_msg}")
            return False, f"Upload error: {error_msg}"
    
    def upload_file(
        self, 
        path: str, 
        file_path: str, 
        upsert: bool = True
    ) -> Tuple[bool, str]:
        """
        Upload pliku z dysku lokalnego.
        
        Args:
            path: Ścieżka docelowa w Storage
            file_path: Ścieżka do pliku na dysku
            upsert: True = nadpisz jeśli istnieje
            
        Returns:
            Tuple (success: bool, path_or_error: str)
        """
        if not os.path.exists(file_path):
            return False, f"Plik nie istnieje: {file_path}"
        
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
        except Exception as e:
            return False, f"Nie można odczytać pliku: {e}"
        
        content_type = get_mime_type(file_path)
        return self.upload(path, data, content_type, upsert)
    
    def upload_compressed(
        self,
        path: str,
        data: bytes,
        content_type: Optional[str] = None,
        upsert: bool = True
    ) -> Tuple[bool, str, Dict]:
        """
        Upload pliku z automatyczną kompresją (jeśli włączona).
        
        Args:
            path: Ścieżka docelowa (BEZ .gz - dodane automatycznie)
            data: Dane binarne pliku
            content_type: MIME type
            upsert: True = nadpisz jeśli istnieje
            
        Returns:
            Tuple (success, actual_path, stats)
            - stats zawiera: original_size, compressed_size, compression_percent
        """
        original_size = len(data)
        
        # Kompresuj jeśli potrzeba
        result = self.compression.compress(data, path)
        
        # Określ ścieżkę (z .gz jeśli skompresowane)
        if result.compression_ratio > 0:
            actual_path = f"{path}.gz"
            upload_content_type = "application/gzip"
        else:
            actual_path = path
            upload_content_type = content_type or get_mime_type(path)
        
        # Upload
        success, upload_result = self.upload(
            actual_path, 
            result.data, 
            upload_content_type, 
            upsert
        )
        
        stats = {
            'original_size': original_size,
            'compressed_size': result.compressed_size,
            'compression_percent': round(result.compression_ratio * 100, 1),
            'is_compressed': result.compression_ratio > 0,
            'actual_path': actual_path if success else None
        }
        
        if success and result.compression_ratio > 0:
            saved_kb = (original_size - result.compressed_size) / 1024
            print(f"[STORAGE] 📦 Compressed: {path} ({result.compression_ratio*100:.0f}% saved, -{saved_kb:.1f} KB)")
        
        return success, upload_result, stats
    
    def download_decompressed(self, path: str) -> Tuple[bool, bytes, Dict]:
        """
        Pobierz plik z automatyczną dekompresją.
        
        Próbuje najpierw .gz, potem oryginalny plik.
        
        Args:
            path: Ścieżka pliku (BEZ .gz)
            
        Returns:
            Tuple (success, data, stats)
        """
        # Najpierw spróbuj wersji skompresowanej
        gz_path = f"{path}.gz"
        success, data = self.download(gz_path)
        
        if success:
            # Dekompresuj
            original_data = self.compression.decompress(data, gz_path)
            stats = {
                'was_compressed': True,
                'compressed_size': len(data),
                'decompressed_size': len(original_data),
                'source_path': gz_path
            }
            return True, original_data, stats
        
        # Spróbuj oryginalnej ścieżki
        success, data = self.download(path)
        if success:
            stats = {
                'was_compressed': False,
                'compressed_size': len(data),
                'decompressed_size': len(data),
                'source_path': path
            }
            return True, data, stats
        
        return False, data, {'error': str(data)}
    
    # =========================================================
    # DOWNLOAD
    # =========================================================
    
    def download(self, path: str) -> Tuple[bool, bytes]:
        """
        Pobierz plik ze Storage.
        
        Args:
            path: Ścieżka w Storage
            
        Returns:
            Tuple (success: bool, data_or_error: bytes/str)
            - success=True: zwraca dane binarne
            - success=False: zwraca komunikat błędu jako bytes
        """
        if not path:
            return False, b"Brak sciezki"
        
        try:
            data = self.client.storage.from_(self.bucket).download(path)
            print(f"[STORAGE] ✅ Download: {path} ({len(data):,} bytes)")
            return True, data
            
        except Exception as e:
            print(f"[STORAGE] ❌ Download failed: {path} - {e}")
            return False, str(e).encode('utf-8')
    
    def download_to_file(self, path: str, local_path: str) -> bool:
        """
        Pobierz plik i zapisz lokalnie na dysku.
        
        Args:
            path: Ścieżka w Storage
            local_path: Ścieżka docelowa na dysku
            
        Returns:
            True jeśli sukces
        """
        success, data = self.download(path)
        if not success:
            return False
        
        try:
            # Utwórz katalogi jeśli nie istnieją
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            with open(local_path, 'wb') as f:
                f.write(data)
            
            print(f"[STORAGE] ✅ Saved to: {local_path}")
            return True
            
        except Exception as e:
            print(f"[STORAGE] ❌ Save failed: {local_path} - {e}")
            return False
    
    # =========================================================
    # BUNDLE - ARCHIWUM PLIKÓW
    # =========================================================
    
    def upload_bundle(
        self,
        path: str,
        files: Dict[str, bytes],
        metadata: Dict = None
    ) -> Tuple[bool, str, Dict]:
        """
        Upload wielu plików jako jedno archiwum ZIP.
        
        Używaj dla strategii BUNDLE - wszystkie pliki produktu
        (oprócz miniatur) w jednym archiwum.
        
        Args:
            path: Ścieżka docelowa (np. products/{id}/files.zip)
            files: Słownik {nazwa_wewnętrzna: dane}
            metadata: Opcjonalne metadane do manifestu
            
        Returns:
            Tuple (success, path, stats)
        """
        if not files:
            return False, "Brak plików do archiwizacji", {}
        
        # Stwórz bundle z manifestem
        bundle_data, manifest = self.compression.create_bundle_with_manifest(files, metadata)
        
        if not bundle_data:
            return False, "Błąd tworzenia archiwum", {}
        
        # Upload
        success, result = self.upload(path, bundle_data, "application/zip", upsert=True)
        
        total_original = sum(len(d) for d in files.values())
        stats = {
            'files_count': len(files),
            'original_size': total_original,
            'bundle_size': len(bundle_data),
            'compression_percent': round((1 - len(bundle_data)/total_original) * 100, 1) if total_original > 0 else 0,
            'manifest': manifest
        }
        
        if success:
            saved_kb = (total_original - len(bundle_data)) / 1024
            print(f"[STORAGE] 📦 Bundle: {len(files)} files -> {path} (-{saved_kb:.1f} KB)")
        
        return success, result, stats
    
    def download_bundle(self, path: str) -> Tuple[bool, Dict[str, bytes], Dict]:
        """
        Pobierz i rozpakuj archiwum.
        
        Args:
            path: Ścieżka do archiwum
            
        Returns:
            Tuple (success, files_dict, stats)
        """
        success, data = self.download(path)
        if not success:
            return False, {}, {'error': 'Download failed'}
        
        # Rozpakuj
        files = self.compression.extract_bundle(data)
        
        # Odczytaj manifest
        manifest = self.compression.read_bundle_manifest(data)
        
        # Usuń manifest z plików
        files.pop('_manifest.json', None)
        
        stats = {
            'files_count': len(files),
            'bundle_size': len(data),
            'total_size': sum(len(d) for d in files.values()),
            'manifest': manifest
        }
        
        return True, files, stats
    
    def download_file_from_bundle(
        self,
        bundle_path: str,
        filename: str
    ) -> Tuple[bool, bytes]:
        """
        Pobierz pojedynczy plik z archiwum.
        
        Args:
            bundle_path: Ścieżka do archiwum
            filename: Nazwa pliku wewnątrz archiwum
            
        Returns:
            Tuple (success, data)
        """
        success, data = self.download(bundle_path)
        if not success:
            return False, b''
        
        file_data = self.compression.extract_single_from_bundle(data, filename)
        if file_data is None:
            return False, b''
        
        return True, file_data
    
    # =========================================================
    # DELETE
    # =========================================================
    
    def delete(self, path: str) -> bool:
        """
        Usuń plik ze Storage.
        
        Args:
            path: Ścieżka w Storage
            
        Returns:
            True jeśli sukces (lub plik nie istniał)
        """
        if not path:
            return False
        
        try:
            self.client.storage.from_(self.bucket).remove([path])
            print(f"[STORAGE] ✅ Delete: {path}")
            
            # Wyczyść cache URL
            self._url_cache.pop(path, None)
            
            return True
            
        except Exception as e:
            # Jeśli plik nie istnieje - to też sukces
            if "not found" in str(e).lower():
                return True
            
            print(f"[STORAGE] ❌ Delete failed: {path} - {e}")
            return False
    
    def delete_multiple(self, paths: List[str]) -> int:
        """
        Usuń wiele plików jednocześnie.
        
        Args:
            paths: Lista ścieżek do usunięcia
            
        Returns:
            Liczba pomyślnie usuniętych plików
        """
        if not paths:
            return 0
        
        deleted = 0
        try:
            self.client.storage.from_(self.bucket).remove(paths)
            deleted = len(paths)
            
            # Wyczyść cache URL
            for path in paths:
                self._url_cache.pop(path, None)
            
            print(f"[STORAGE] ✅ Deleted {deleted} files")
            
        except Exception as e:
            print(f"[STORAGE] ❌ Batch delete failed: {e}")
            # Spróbuj usunąć pojedynczo
            for path in paths:
                if self.delete(path):
                    deleted += 1
        
        return deleted
    
    def delete_folder(self, folder_path: str) -> int:
        """
        Usuń wszystkie pliki w folderze (rekurencyjnie).
        
        Args:
            folder_path: Ścieżka do folderu (np. "products/{id}")
            
        Returns:
            Liczba usuniętych plików
        """
        files = self.list_files(folder_path, recursive=True)
        
        if not files:
            return 0
        
        paths = [f['path'] for f in files]
        return self.delete_multiple(paths)
    
    # =========================================================
    # LIST / EXISTS
    # =========================================================
    
    def exists(self, path: str) -> bool:
        """
        Sprawdź czy plik istnieje w Storage.
        
        Args:
            path: Ścieżka w Storage
            
        Returns:
            True jeśli plik istnieje
        """
        if not path:
            return False
        
        try:
            folder = str(Path(path).parent)
            filename = Path(path).name
            
            files = self.client.storage.from_(self.bucket).list(folder)
            return any(f['name'] == filename for f in files)
            
        except Exception:
            return False
    
    def list_files(
        self, 
        folder_path: str, 
        recursive: bool = False
    ) -> List[Dict]:
        """
        Listuj pliki w folderze.
        
        Args:
            folder_path: Ścieżka do folderu
            recursive: True = uwzględnij podfoldery
            
        Returns:
            Lista słowników z informacjami o plikach:
            [{'name': str, 'path': str, 'size': int, 'mimetype': str, ...}]
        """
        results = []
        
        try:
            items = self.client.storage.from_(self.bucket).list(folder_path)
            
            for item in items:
                item_path = f"{folder_path}/{item['name']}"
                
                # Sprawdź czy to plik (ma metadata) czy folder
                if item.get('metadata'):
                    # To jest plik
                    results.append({
                        'name': item['name'],
                        'path': item_path,
                        'size': item.get('metadata', {}).get('size', 0),
                        'mimetype': item.get('metadata', {}).get('mimetype', ''),
                        'created_at': item.get('created_at'),
                        'updated_at': item.get('updated_at'),
                    })
                elif recursive:
                    # To jest folder - rekurencja
                    results.extend(self.list_files(item_path, recursive=True))
            
        except Exception as e:
            print(f"[STORAGE] ⚠️ List failed: {folder_path} - {e}")
        
        return results
    
    # =========================================================
    # URL GENERATION
    # =========================================================
    
    def get_public_url(self, path: str) -> str:
        """
        Generuj publiczny URL dla pliku.
        
        UWAGA: Wymaga publicznego bucketa lub publicznej polityki RLS!
        
        Args:
            path: Ścieżka w Storage
            
        Returns:
            Publiczny URL (pusty string jeśli brak ścieżki)
        """
        if not path:
            return ""
        return StoragePaths.get_public_url(path)
    
    def get_signed_url(
        self, 
        path: str, 
        expires_in: int = URL_CACHE_TTL,
        use_cache: bool = True
    ) -> Optional[str]:
        """
        Generuj podpisany (tymczasowy) URL dla pliku.
        
        Używaj dla plików niepublicznych.
        
        Args:
            path: Ścieżka w Storage
            expires_in: Czas ważności w sekundach (domyślnie 24h)
            use_cache: Użyj cache dla URL (zalecane)
            
        Returns:
            Podpisany URL lub None w przypadku błędu
        """
        if not path:
            return None
        
        # Sprawdź cache
        if use_cache and path in self._url_cache:
            cached_url, cached_time = self._url_cache[path]
            # URL ważny jeśli nie minęło 90% czasu
            if datetime.now() - cached_time < timedelta(seconds=expires_in * 0.9):
                return cached_url
        
        try:
            response = self.client.storage.from_(self.bucket).create_signed_url(
                path, expires_in
            )
            url = response.get('signedURL')
            
            # Zapisz do cache
            if url and use_cache:
                self._url_cache[path] = (url, datetime.now())
            
            return url
            
        except Exception as e:
            print(f"[STORAGE] ❌ Signed URL failed: {path} - {e}")
            return None
    
    def clear_url_cache(self):
        """Wyczyść cache URL (np. po dłuższym czasie nieaktywności)"""
        self._url_cache.clear()
        print("[STORAGE] Cache URL wyczyszczony")
    
    # =========================================================
    # BULK OPERATIONS
    # =========================================================
    
    def upload_product_files(
        self, 
        product_id: str, 
        files: Dict[str, bytes],
        extensions: Dict[str, str] = None
    ) -> Dict[str, Tuple[bool, str]]:
        """
        Upload wielu plików produktu jednocześnie.
        
        Args:
            product_id: UUID produktu
            files: Słownik {typ: dane}, np. {'cad_2d': bytes, 'thumbnail_100': bytes}
            extensions: Słownik rozszerzeń {typ: ext}, np. {'cad_2d': 'dxf'}
            
        Returns:
            Słownik wyników {typ: (success, path_or_error)}
        """
        extensions = extensions or {}
        results = {}
        
        # Mapowanie typów na metody generowania ścieżek
        path_generators = {
            'cad_2d': lambda: StoragePaths.cad_2d(
                product_id, extensions.get('cad_2d', 'dxf')
            ),
            'cad_3d': lambda: StoragePaths.cad_3d(
                product_id, extensions.get('cad_3d', 'step')
            ),
            'user_image': lambda: StoragePaths.user_image(
                product_id, extensions.get('user_image', 'png')
            ),
            'thumbnail_100': lambda: StoragePaths.thumbnail_100(product_id),
            'preview_800': lambda: StoragePaths.preview_800(product_id),
            'preview_4k': lambda: StoragePaths.preview_4k(product_id),
        }
        
        for file_type, data in files.items():
            if not data:
                continue
            
            if file_type in path_generators:
                path = path_generators[file_type]()
                results[file_type] = self.upload(path, data, upsert=True)
            else:
                results[file_type] = (False, f"Nieznany typ pliku: {file_type}")
        
        # Podsumowanie
        success_count = sum(1 for s, _ in results.values() if s)
        print(f"[STORAGE] Uploaded {success_count}/{len(results)} product files")
        
        return results
    
    def delete_product_files(self, product_id: str) -> int:
        """
        Usuń wszystkie pliki produktu ze Storage.
        
        Args:
            product_id: UUID produktu
            
        Returns:
            Liczba usuniętych plików
        """
        folder = StoragePaths.product_folder(product_id)
        return self.delete_folder(folder)
    
    def get_product_files_info(self, product_id: str) -> Dict[str, Optional[Dict]]:
        """
        Pobierz informacje o wszystkich plikach produktu.
        
        Args:
            product_id: UUID produktu
            
        Returns:
            Słownik z informacjami o plikach wg typu
        """
        files = self.list_files(
            StoragePaths.product_folder(product_id), 
            recursive=True
        )
        
        result = {
            'cad_2d': None,
            'cad_3d': None,
            'user_image': None,
            'thumbnail_100': None,
            'preview_800': None,
            'preview_4k': None,
            'attachments': [],
        }
        
        for f in files:
            path = f['path']
            file_type = StoragePaths.get_file_type_from_path(path)
            
            if file_type == 'cad_2d':
                result['cad_2d'] = f
            elif file_type == 'cad_3d':
                result['cad_3d'] = f
            elif file_type == 'user_image':
                result['user_image'] = f
            elif file_type == 'thumbnail':
                if 'thumbnail_100' in path:
                    result['thumbnail_100'] = f
                elif 'preview_800' in path:
                    result['preview_800'] = f
                elif 'preview_4k' in path:
                    result['preview_4k'] = f
            elif file_type == 'attachment':
                result['attachments'].append(f)
        
        return result


# =========================================================
# TESTY
# =========================================================

if __name__ == "__main__":
    print("StorageRepository - moduł dostępu do Supabase Storage")
    print("Użyj: storage = StorageRepository(get_supabase_client())")
