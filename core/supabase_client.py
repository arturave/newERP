#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Centralny moduł połączenia z Supabase

Singleton pattern - jeden klient dla całej aplikacji.
Używa SERVICE_ROLE_KEY dla pełnych uprawnień (obejście RLS).
"""

from typing import Optional
from supabase import create_client, Client

from config.settings import SUPABASE_URL, SUPABASE_SERVICE_KEY


# Globalny klient Supabase
_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """
    Zwraca singleton instancję klienta Supabase.
    
    Klient używa SERVICE_ROLE_KEY co daje pełne uprawnienia
    i omija Row Level Security (RLS).
    
    Returns:
        Client: Klient Supabase z pełnymi uprawnieniami
        
    Raises:
        ValueError: Jeśli brak konfiguracji
    """
    global _supabase_client
    
    if _supabase_client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise ValueError(
                "[ERROR] Brak konfiguracji Supabase!\n"
                "Sprawdź SUPABASE_URL i SUPABASE_SERVICE_KEY w config/settings.py lub .env"
            )
        
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        print("[OK] Połączono z Supabase (SERVICE_ROLE - pełne uprawnienia)")
    
    return _supabase_client


def reset_client():
    """
    Resetuj klienta (przydatne do testów).
    """
    global _supabase_client
    _supabase_client = None


# Aliasy dla kompatybilności
supabase = property(lambda self: get_supabase_client())


def ensure_authenticated() -> Client:
    """
    Funkcja dla kompatybilności ze starym kodem.
    
    Returns:
        Client: Klient Supabase
    """
    return get_supabase_client()


def get_auth_client() -> Client:
    """
    Alias dla kompatybilności.
    
    Returns:
        Client: Klient Supabase
    """
    return get_supabase_client()


def test_connection() -> bool:
    """
    Testuj połączenie z Supabase.
    
    Returns:
        True jeśli połączenie działa
    """
    try:
        client = get_supabase_client()
        
        # Prosty test - sprawdź czy można wykonać zapytanie
        response = client.table('materials_dict').select("id").limit(1).execute()
        
        print("[OK] Test połączenia zakończony sukcesem")
        return True
        
    except Exception as e:
        print(f"[ERROR] Test połączenia nie powiódł się: {e}")
        return False


# ============================================================
# TESTY
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("TEST POŁĄCZENIA Z SUPABASE")
    print("=" * 60)
    
    try:
        client = get_supabase_client()
        print(f"[OK] URL: {SUPABASE_URL}")
        print("[OK] Używam SERVICE_ROLE_KEY (pełne uprawnienia)")
        
        # Test dostępu do tabel
        tables_to_test = [
            'materials_dict',
            'customers', 
            'products_catalog',
            'orders'
        ]
        
        print("\nTest dostępu do tabel:")
        for table in tables_to_test:
            try:
                response = client.table(table).select("*").limit(1).execute()
                count = len(response.data) if response.data else 0
                print(f"  [OK] {table}: dostęp OK ({count} rekord)")
            except Exception as e:
                print(f"  [ERROR] {table}: {e}")
        
        # Test Storage
        print("\nTest Storage:")
        try:
            buckets = client.storage.list_buckets()
            bucket_names = [b.name for b in buckets]
            print(f"  [OK] Dostępne buckety: {bucket_names}")
        except Exception as e:
            print(f"  [ERROR] Storage: {e}")
        
        print("\n" + "=" * 60)
        print("[OK] Moduł supabase_client gotowy do użycia!")
        print("=" * 60)
        
    except Exception as e:
        print(f"[ERROR] {e}")
