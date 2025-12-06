#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Moduł kompresji plików CAD i załączników.

Trzy strategie kompresji:
1. INDIVIDUAL - każdy plik kompresowany osobno (gzip)
2. BUNDLE - wszystkie pliki w jednym archiwum (bez miniatur)
3. HYBRID - CAD i źródła skompresowane, miniatury nie

Zalety gzip:
- Wbudowany w Python (brak zależności)
- Streaming support
- Natywna obsługa HTTP (Content-Encoding: gzip)
- Szybka kompresja/dekompresja
- 70-85% kompresji dla plików CAD (tekstowych)
"""

import gzip
import io
import zipfile
import json
from enum import Enum
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass
from pathlib import Path


class CompressionStrategy(Enum):
    """Strategia kompresji plików"""
    NONE = "none"           # Bez kompresji
    INDIVIDUAL = "individual"  # Każdy plik osobno (.gz)
    BUNDLE = "bundle"       # Wszystko w jednym archiwum (.zip)
    HYBRID = "hybrid"       # CAD skompresowane, miniatury nie


@dataclass
class CompressionResult:
    """Wynik kompresji"""
    success: bool
    data: bytes
    original_size: int
    compressed_size: int
    compression_ratio: float  # 0.0 - 1.0 (1.0 = 100% kompresji)
    
    @property
    def saved_bytes(self) -> int:
        return self.original_size - self.compressed_size
    
    @property
    def saved_percent(self) -> float:
        if self.original_size == 0:
            return 0.0
        return (self.saved_bytes / self.original_size) * 100


class CompressionManager:
    """
    Manager kompresji plików.
    
    Obsługuje trzy strategie kompresji:
    - INDIVIDUAL: każdy plik .gz osobno
    - BUNDLE: wszystkie pliki w .zip
    - HYBRID: CAD w .gz, miniatury bez kompresji
    
    Example:
        manager = CompressionManager(CompressionStrategy.HYBRID)
        
        # Kompresja pojedynczego pliku
        result = manager.compress(data, "model.step")
        
        # Dekompresja
        original = manager.decompress(result.data, "model.step.gz")
    """
    
    # Rozszerzenia plików CAD (tekstowe, dobrze się kompresują)
    CAD_EXTENSIONS = {'.dxf', '.dwg', '.step', '.stp', '.iges', '.igs'}
    
    # Rozszerzenia obrazów źródłowych (kompresja mniej efektywna ale warto)
    IMAGE_EXTENSIONS = {'.png', '.bmp', '.tiff', '.svg'}
    
    # Nie kompresuj (już skompresowane)
    NO_COMPRESS_EXTENSIONS = {'.jpg', '.jpeg', '.gif', '.webp', '.zip', '.7z', '.rar', '.gz'}
    
    # Miniatury - nigdy nie kompresuj (szybki dostęp)
    THUMBNAIL_PATTERNS = {'thumbnail_', 'preview_'}
    
    def __init__(self, strategy: CompressionStrategy = CompressionStrategy.HYBRID):
        """
        Inicjalizacja managera.
        
        Args:
            strategy: Strategia kompresji
        """
        self.strategy = strategy
        self.compression_level = 6  # 1-9, 6 = dobry balans
    
    # =========================================================
    # PUBLIC API - POJEDYNCZE PLIKI
    # =========================================================
    
    def should_compress(self, filename: str) -> bool:
        """
        Sprawdź czy plik powinien być skompresowany.
        
        Args:
            filename: Nazwa pliku lub ścieżka
            
        Returns:
            True jeśli plik powinien być skompresowany
        """
        if self.strategy == CompressionStrategy.NONE:
            return False
        
        name = Path(filename).name.lower()
        ext = Path(filename).suffix.lower()
        
        # Nie kompresuj miniatur
        if any(pattern in name for pattern in self.THUMBNAIL_PATTERNS):
            return False
        
        # Nie kompresuj już skompresowanych
        if ext in self.NO_COMPRESS_EXTENSIONS:
            return False
        
        # Strategia INDIVIDUAL/HYBRID - kompresuj CAD i obrazy źródłowe
        if self.strategy in (CompressionStrategy.INDIVIDUAL, CompressionStrategy.HYBRID):
            return ext in self.CAD_EXTENSIONS or ext in self.IMAGE_EXTENSIONS
        
        # BUNDLE - wszystko idzie do archiwum
        return True
    
    def compress(self, data: bytes, filename: str) -> CompressionResult:
        """
        Kompresuj dane pliku.
        
        Args:
            data: Dane binarne pliku
            filename: Nazwa pliku (do określenia typu)
            
        Returns:
            CompressionResult z danymi i statystykami
        """
        original_size = len(data)
        
        if not self.should_compress(filename):
            return CompressionResult(
                success=True,
                data=data,
                original_size=original_size,
                compressed_size=original_size,
                compression_ratio=0.0
            )
        
        try:
            compressed = self._gzip_compress(data)
            compressed_size = len(compressed)
            
            # Jeśli kompresja nie pomogła, zwróć oryginał
            if compressed_size >= original_size:
                return CompressionResult(
                    success=True,
                    data=data,
                    original_size=original_size,
                    compressed_size=original_size,
                    compression_ratio=0.0
                )
            
            ratio = 1.0 - (compressed_size / original_size)
            
            return CompressionResult(
                success=True,
                data=compressed,
                original_size=original_size,
                compressed_size=compressed_size,
                compression_ratio=ratio
            )
            
        except Exception as e:
            print(f"[COMPRESS] ❌ Błąd kompresji {filename}: {e}")
            return CompressionResult(
                success=False,
                data=data,
                original_size=original_size,
                compressed_size=original_size,
                compression_ratio=0.0
            )
    
    def decompress(self, data: bytes, filename: str) -> bytes:
        """
        Dekompresuj dane pliku.
        
        Args:
            data: Dane (skompresowane lub nie)
            filename: Nazwa pliku
            
        Returns:
            Zdekompresowane dane
        """
        # Sprawdź czy to gzip po magic bytes
        if self._is_gzip(data):
            try:
                return self._gzip_decompress(data)
            except Exception as e:
                print(f"[COMPRESS] ⚠️ Błąd dekompresji {filename}: {e}")
                return data
        
        return data
    
    def get_storage_filename(self, original_filename: str) -> str:
        """
        Pobierz nazwę pliku do przechowywania (z .gz jeśli kompresowany).
        
        Args:
            original_filename: Oryginalna nazwa pliku
            
        Returns:
            Nazwa do Storage (może mieć .gz)
        """
        if self.should_compress(original_filename):
            return f"{original_filename}.gz"
        return original_filename
    
    def get_original_filename(self, storage_filename: str) -> str:
        """
        Pobierz oryginalną nazwę pliku (usuń .gz).
        
        Args:
            storage_filename: Nazwa w Storage
            
        Returns:
            Oryginalna nazwa
        """
        if storage_filename.endswith('.gz'):
            return storage_filename[:-3]
        return storage_filename
    
    # =========================================================
    # PUBLIC API - BUNDLE (ARCHIWUM)
    # =========================================================
    
    def create_bundle(
        self, 
        files: Dict[str, bytes],
        exclude_patterns: List[str] = None
    ) -> CompressionResult:
        """
        Stwórz archiwum ZIP ze wszystkich plików.
        
        Args:
            files: Słownik {nazwa: dane}
            exclude_patterns: Wzorce do wykluczenia (np. ['thumbnail_'])
            
        Returns:
            CompressionResult z archiwum ZIP
        """
        exclude = exclude_patterns or list(self.THUMBNAIL_PATTERNS)
        
        total_original = 0
        included_files = {}
        
        for name, data in files.items():
            # Sprawdź wykluczenia
            if any(pattern in name.lower() for pattern in exclude):
                continue
            
            total_original += len(data)
            included_files[name] = data
        
        if not included_files:
            return CompressionResult(
                success=True,
                data=b'',
                original_size=0,
                compressed_size=0,
                compression_ratio=0.0
            )
        
        try:
            buffer = io.BytesIO()
            
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=self.compression_level) as zf:
                for name, data in included_files.items():
                    zf.writestr(name, data)
            
            compressed = buffer.getvalue()
            compressed_size = len(compressed)
            ratio = 1.0 - (compressed_size / total_original) if total_original > 0 else 0.0
            
            return CompressionResult(
                success=True,
                data=compressed,
                original_size=total_original,
                compressed_size=compressed_size,
                compression_ratio=ratio
            )
            
        except Exception as e:
            print(f"[COMPRESS] ❌ Błąd tworzenia bundle: {e}")
            return CompressionResult(
                success=False,
                data=b'',
                original_size=total_original,
                compressed_size=0,
                compression_ratio=0.0
            )
    
    def extract_bundle(self, bundle_data: bytes) -> Dict[str, bytes]:
        """
        Wypakuj archiwum ZIP.
        
        Args:
            bundle_data: Dane archiwum ZIP
            
        Returns:
            Słownik {nazwa: dane}
        """
        if not bundle_data:
            return {}
        
        try:
            buffer = io.BytesIO(bundle_data)
            files = {}
            
            with zipfile.ZipFile(buffer, 'r') as zf:
                for name in zf.namelist():
                    files[name] = zf.read(name)
            
            return files
            
        except Exception as e:
            print(f"[COMPRESS] ❌ Błąd rozpakowywania bundle: {e}")
            return {}
    
    def extract_single_from_bundle(self, bundle_data: bytes, filename: str) -> Optional[bytes]:
        """
        Wypakuj pojedynczy plik z archiwum.
        
        Args:
            bundle_data: Dane archiwum ZIP
            filename: Nazwa pliku do wypakowania
            
        Returns:
            Dane pliku lub None
        """
        if not bundle_data:
            return None
        
        try:
            buffer = io.BytesIO(bundle_data)
            
            with zipfile.ZipFile(buffer, 'r') as zf:
                if filename in zf.namelist():
                    return zf.read(filename)
            
            return None
            
        except Exception as e:
            print(f"[COMPRESS] ❌ Błąd wypakowania {filename}: {e}")
            return None
    
    # =========================================================
    # PUBLIC API - BUNDLE MANIFEST
    # =========================================================
    
    def create_bundle_with_manifest(
        self,
        files: Dict[str, bytes],
        metadata: Dict = None
    ) -> Tuple[bytes, Dict]:
        """
        Stwórz bundle z manifestem opisującym zawartość.
        
        Args:
            files: Słownik {nazwa: dane}
            metadata: Dodatkowe metadane
            
        Returns:
            Tuple (bundle_data, manifest)
        """
        manifest = {
            'version': '1.0',
            'strategy': self.strategy.value,
            'files': {},
            'metadata': metadata or {}
        }
        
        for name, data in files.items():
            manifest['files'][name] = {
                'size': len(data),
                'compressed': self.should_compress(name)
            }
        
        # Dodaj manifest do bundle
        files_with_manifest = dict(files)
        files_with_manifest['_manifest.json'] = json.dumps(manifest, indent=2).encode('utf-8')
        
        result = self.create_bundle(files_with_manifest, exclude_patterns=[])
        
        return result.data, manifest
    
    def read_bundle_manifest(self, bundle_data: bytes) -> Optional[Dict]:
        """
        Odczytaj manifest z bundle.
        
        Args:
            bundle_data: Dane archiwum
            
        Returns:
            Manifest lub None
        """
        manifest_data = self.extract_single_from_bundle(bundle_data, '_manifest.json')
        if manifest_data:
            try:
                return json.loads(manifest_data.decode('utf-8'))
            except Exception:
                pass
        return None
    
    # =========================================================
    # PRIVATE - GZIP
    # =========================================================
    
    def _gzip_compress(self, data: bytes) -> bytes:
        """Kompresuj dane gzip"""
        buffer = io.BytesIO()
        with gzip.GzipFile(fileobj=buffer, mode='wb', compresslevel=self.compression_level) as gz:
            gz.write(data)
        return buffer.getvalue()
    
    def _gzip_decompress(self, data: bytes) -> bytes:
        """Dekompresuj dane gzip"""
        buffer = io.BytesIO(data)
        with gzip.GzipFile(fileobj=buffer, mode='rb') as gz:
            return gz.read()
    
    def _is_gzip(self, data: bytes) -> bool:
        """Sprawdź czy dane to gzip (magic bytes)"""
        return len(data) >= 2 and data[0:2] == b'\x1f\x8b'


# =========================================================
# FACTORY
# =========================================================

def create_compression_manager(
    strategy: str = "hybrid"
) -> CompressionManager:
    """
    Factory do tworzenia CompressionManager.
    
    Args:
        strategy: "none", "individual", "bundle", "hybrid"
        
    Returns:
        CompressionManager z wybraną strategią
    """
    strategy_map = {
        'none': CompressionStrategy.NONE,
        'individual': CompressionStrategy.INDIVIDUAL,
        'bundle': CompressionStrategy.BUNDLE,
        'hybrid': CompressionStrategy.HYBRID,
    }
    
    strat = strategy_map.get(strategy.lower(), CompressionStrategy.HYBRID)
    return CompressionManager(strat)


# =========================================================
# UTILITY FUNCTIONS
# =========================================================

def compress_file(data: bytes, filename: str) -> Tuple[bytes, bool]:
    """
    Szybka funkcja do kompresji pojedynczego pliku.
    
    Args:
        data: Dane pliku
        filename: Nazwa pliku
        
    Returns:
        Tuple (compressed_data, was_compressed)
    """
    manager = CompressionManager(CompressionStrategy.HYBRID)
    result = manager.compress(data, filename)
    return result.data, result.compression_ratio > 0


def decompress_file(data: bytes, filename: str) -> bytes:
    """
    Szybka funkcja do dekompresji pliku.
    
    Args:
        data: Dane (mogą być skompresowane)
        filename: Nazwa pliku
        
    Returns:
        Zdekompresowane dane
    """
    manager = CompressionManager()
    return manager.decompress(data, filename)


def get_compression_stats(original: bytes, compressed: bytes) -> Dict:
    """
    Pobierz statystyki kompresji.
    
    Args:
        original: Oryginalne dane
        compressed: Skompresowane dane
        
    Returns:
        Słownik ze statystykami
    """
    orig_size = len(original)
    comp_size = len(compressed)
    saved = orig_size - comp_size
    ratio = (saved / orig_size * 100) if orig_size > 0 else 0
    
    return {
        'original_size': orig_size,
        'compressed_size': comp_size,
        'saved_bytes': saved,
        'compression_percent': round(ratio, 1),
        'is_compressed': comp_size < orig_size
    }
