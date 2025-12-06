#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Products Module - Moduł zarządzania produktami

Architektura (Clean Architecture):
─────────────────────────────────────────────────────────────
    GUI Layer (products.gui)
         │
         ▼
    ProductService (products.service) ← Główny punkt wejścia
         │
         ├───────────────────┐
         ▼                   ▼
    ProductRepository    StorageRepository
    (products.repository) (products.storage)
         │                   │
         ▼                   ▼
    Supabase DB          Supabase Storage
─────────────────────────────────────────────────────────────

Użycie:
    # Najprostsze - użyj factory
    from products import create_product_service
    
    service = create_product_service()
    
    # Utwórz produkt
    success, product_id = service.create_product(
        data={'name': 'Wspornik A', 'thickness_mm': 2.0, 'material_id': 'xxx'},
        files={'cad_2d': dxf_bytes},
        file_extensions={'cad_2d': 'dxf'}
    )
    
    # Pobierz produkt z URL
    product = service.get_product(product_id)
    print(product['thumbnail_100_url'])
    
    # Lista z filtrami
    products = service.list_products(
        filters={'category': 'BLACHY'},
        search='wspornik',
        limit=20
    )
    
    # Dodaj załącznik
    success, att_id = service.add_attachment(
        product_id, 
        pdf_bytes, 
        'dokumentacja.pdf',
        note='Dokumentacja techniczna'
    )

Dla zaawansowanych przypadków - bezpośredni dostęp do repozytoriów:
    from products import ProductRepository, StorageRepository, StoragePaths
    from core import get_supabase_client
    
    client = get_supabase_client()
    repo = ProductRepository(client)
    storage = StorageRepository(client)
    
    # Generuj ścieżkę
    path = StoragePaths.cad_2d(product_id, 'dxf')
"""

# Główny serwis i factory
from products.service import ProductService, create_product_service

# Repozytoria (dla zaawansowanych przypadków)
from products.repository import ProductRepository
from products.storage import StorageRepository

# Ścieżki Storage
from products.paths import StoragePaths

# Eksportowane symbole
__all__ = [
    # Główny punkt wejścia
    'ProductService',
    'create_product_service',
    
    # Repozytoria
    'ProductRepository',
    'StorageRepository',
    
    # Pomocnicze
    'StoragePaths',
]

# Wersja modułu
__version__ = '2.0.0'
__author__ = 'NewERP Team'
