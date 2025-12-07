#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProductRepository - Warstwa dostępu do tabeli products_catalog

Odpowiedzialność:
- CRUD operacje na produktach
- Zapytania z filtrami i paginacją
- Operacje na załącznikach (tabela product_attachments)
- Generowanie kodów indeksowych

Zasady:
- Przechowuje ŚCIEŻKI (path), nie URL
- Zwraca surowe dane z bazy (dict)
- Nie zarządza plikami (to robi StorageRepository)
- Graceful error handling (zwraca None zamiast wyjątków)
"""

from typing import Optional, List, Dict, Any, Tuple, Set
from datetime import datetime
import getpass

from supabase import Client


class ProductRepository:
    """
    Repository dla tabeli products_catalog i product_attachments.
    
    Wszystkie metody zwracają dict/list/None - nie rzucają wyjątków.
    
    Example:
        from core import get_supabase_client
        from products.repository import ProductRepository
        
        client = get_supabase_client()
        repo = ProductRepository(client)
        
        # Utwórz produkt
        product_id = repo.create({'name': 'Test', 'thickness_mm': 2.0})
        
        # Pobierz produkt
        product = repo.get_by_id(product_id)
        
        # Lista z filtrami
        products = repo.list(filters={'category': 'BLACHY'}, search='wspornik')
    """
    
    TABLE = "products_catalog"
    ATTACHMENTS_TABLE = "product_attachments"
    
    def __init__(self, client: Client):
        """
        Inicjalizacja z klientem Supabase.
        
        Args:
            client: Instancja Supabase Client
        """
        self.client = client
    
    # =========================================================
    # CREATE
    # =========================================================
    
    def create(self, data: Dict[str, Any]) -> Optional[str]:
        """
        Utwórz nowy produkt w bazie.
        
        Args:
            data: Dane produktu (bez 'id' - generowane przez bazę)
            
        Returns:
            UUID nowego produktu lub None w przypadku błędu
        """
        try:
            # Dodaj pola audytu
            data['created_by'] = self._get_current_user()
            data['updated_by'] = data['created_by']
            data['created_at'] = datetime.now().isoformat()
            data['updated_at'] = data['created_at']
            data['is_active'] = True
            
            # Usuń wartości None (Supabase ich nie lubi)
            clean_data = {k: v for k, v in data.items() if v is not None}
            
            response = self.client.table(self.TABLE).insert(clean_data).execute()
            
            if response.data and len(response.data) > 0:
                product_id = response.data[0].get('id')
                print(f"[DB] ✅ Product created: {product_id}")
                return product_id
            
            print("[DB] ❌ Create failed: No data returned")
            return None
            
        except Exception as e:
            print(f"[DB] ❌ Create product failed: {e}")
            return None

    def create_batch(self, products: List[Dict[str, Any]]) -> List[str]:
        """
        Batch insert produktów (optymalizacja: 1 zapytanie).

        Args:
            products: Lista danych produktów

        Returns:
            Lista UUID utworzonych produktów
        """
        if not products:
            return []

        try:
            # Dodaj pola audytu do wszystkich
            current_user = self._get_current_user()
            now = datetime.now().isoformat()

            for p in products:
                p.setdefault('created_by', current_user)
                p.setdefault('updated_by', current_user)
                p.setdefault('created_at', now)
                p.setdefault('updated_at', now)
                p.setdefault('is_active', True)

            # Usuń wartości None
            clean_products = [
                {k: v for k, v in p.items() if v is not None}
                for p in products
            ]

            response = self.client.table(self.TABLE).insert(clean_products).execute()

            if response.data:
                ids = [row['id'] for row in response.data]
                print(f"[DB] ✅ Batch created {len(ids)} products")
                return ids

            return []

        except Exception as e:
            print(f"[DB] ❌ Batch create failed: {e}")
            return []

    def find_existing_batch(self, specs: List[Tuple[str, float]]) -> Dict[Tuple[str, float], str]:
        """
        Batch znajdź istniejące produkty po (name, thickness).

        Optymalizacja: 1 zapytanie zamiast N.

        Args:
            specs: Lista krotek (nazwa, grubość)

        Returns:
            Dict[(name, thickness)] -> product_id
        """
        if not specs:
            return {}

        try:
            # Pobierz unikalne grubości
            thicknesses = list(set(s[1] for s in specs))

            response = self.client.table(self.TABLE)\
                .select('id, name, thickness_mm')\
                .eq('is_active', True)\
                .in_('thickness_mm', thicknesses)\
                .execute()

            # Buduj mapę wyników
            result = {}
            specs_set = set(specs)

            for row in response.data or []:
                key = (row['name'], float(row['thickness_mm']))
                if key in specs_set:
                    result[key] = row['id']

            print(f"[DB] Found {len(result)}/{len(specs)} existing products")
            return result

        except Exception as e:
            print(f"[DB] ❌ find_existing_batch failed: {e}")
            return {}

    # =========================================================
    # READ
    # =========================================================
    
    def get_by_id(self, product_id: str) -> Optional[Dict]:
        """
        Pobierz produkt po UUID.
        
        Automatycznie dołącza nazwę materiału z tabeli materials_dict.
        
        Args:
            product_id: UUID produktu
            
        Returns:
            Dane produktu lub None
        """
        try:
            response = self.client.table(self.TABLE)\
                .select("*, materials_dict(id, name)")\
                .eq('id', product_id)\
                .single()\
                .execute()
            
            return response.data if response.data else None
            
        except Exception as e:
            print(f"[DB] ❌ Get product failed: {product_id} - {e}")
            return None
    
    def get_by_idx_code(self, idx_code: str) -> Optional[Dict]:
        """
        Pobierz produkt po kodzie indeksowym.
        
        Args:
            idx_code: Kod indeksowy (np. PC-202411-0001)
            
        Returns:
            Dane produktu lub None
        """
        try:
            response = self.client.table(self.TABLE)\
                .select("*, materials_dict(id, name)")\
                .eq('idx_code', idx_code)\
                .single()\
                .execute()
            
            return response.data if response.data else None
            
        except Exception as e:
            print(f"[DB] ❌ Get product by idx_code failed: {idx_code} - {e}")
            return None
    
    def list(
        self, 
        filters: Dict[str, Any] = None,
        search: str = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "created_at",
        ascending: bool = False,
        active_only: bool = True
    ) -> List[Dict]:
        """
        Lista produktów z filtrami i paginacją.
        
        Args:
            filters: Słownik filtrów {kolumna: wartość}
            search: Tekst do wyszukania (nazwa, kod, kategoria, opis)
            limit: Maksymalna liczba wyników
            offset: Przesunięcie (dla paginacji)
            order_by: Kolumna sortowania
            ascending: True = rosnąco, False = malejąco
            active_only: True = tylko aktywne produkty
            
        Returns:
            Lista produktów (pusta lista w przypadku błędu)
        """
        try:
            query = self.client.table(self.TABLE)\
                .select("*, materials_dict(id, name)")
            
            # Filtr aktywności
            if active_only:
                query = query.eq('is_active', True)
            
            # Filtry dokładne
            if filters:
                for col, val in filters.items():
                    if val is not None:
                        query = query.eq(col, val)
            
            # Wyszukiwanie tekstowe (ILIKE = case-insensitive)
            if search:
                search_pattern = f"%{search}%"
                query = query.or_(
                    f"name.ilike.{search_pattern},"
                    f"idx_code.ilike.{search_pattern},"
                    f"category.ilike.{search_pattern},"
                    f"description.ilike.{search_pattern}"
                )
            
            # Sortowanie
            query = query.order(order_by, desc=not ascending)
            
            # Paginacja
            query = query.range(offset, offset + limit - 1)
            
            response = query.execute()
            return response.data if response.data else []
            
        except Exception as e:
            print(f"[DB] ❌ List products failed: {e}")
            return []
    
    def count(
        self, 
        filters: Dict[str, Any] = None, 
        search: str = None,
        active_only: bool = True
    ) -> int:
        """
        Policz produkty (z filtrami).
        
        Args:
            filters: Słownik filtrów
            search: Tekst wyszukiwania
            active_only: True = tylko aktywne
            
        Returns:
            Liczba produktów (0 w przypadku błędu)
        """
        try:
            query = self.client.table(self.TABLE).select("id", count="exact")
            
            if active_only:
                query = query.eq('is_active', True)
            
            if filters:
                for col, val in filters.items():
                    if val is not None:
                        query = query.eq(col, val)
            
            if search:
                search_pattern = f"%{search}%"
                query = query.or_(
                    f"name.ilike.{search_pattern},"
                    f"idx_code.ilike.{search_pattern}"
                )
            
            response = query.execute()
            return response.count or 0
            
        except Exception as e:
            print(f"[DB] ❌ Count products failed: {e}")
            return 0
    
    # =========================================================
    # UPDATE
    # =========================================================
    
    def update(self, product_id: str, data: Dict[str, Any]) -> bool:
        """
        Zaktualizuj produkt.
        
        Args:
            product_id: UUID produktu
            data: Dane do aktualizacji
            
        Returns:
            True jeśli sukces
        """
        try:
            # Dodaj pole audytu
            data['updated_by'] = self._get_current_user()
            data['updated_at'] = datetime.now().isoformat()
            
            # Usuń pola tylko do odczytu i wartości None
            readonly_fields = {'id', 'created_at', 'created_by'}
            clean_data = {
                k: v for k, v in data.items() 
                if k not in readonly_fields and v is not None
            }
            
            if not clean_data:
                return True  # Nic do aktualizacji
            
            response = self.client.table(self.TABLE)\
                .update(clean_data)\
                .eq('id', product_id)\
                .execute()
            
            if response.data:
                print(f"[DB] ✅ Product updated: {product_id}")
                return True
            
            return False
            
        except Exception as e:
            print(f"[DB] ❌ Update product failed: {product_id} - {e}")
            return False
    
    def update_paths(self, product_id: str, paths: Dict[str, str]) -> bool:
        """
        Zaktualizuj ścieżki plików produktu.
        
        Args:
            product_id: UUID produktu
            paths: Słownik ścieżek {cad_2d_path: 'xxx', ...}
            
        Returns:
            True jeśli sukces
        """
        # Walidacja nazw kolumn - tylko dozwolone kolumny PATH
        valid_path_columns = {
            'cad_2d_path', 'cad_3d_path', 'user_image_path',
            'thumbnail_100_path', 'preview_800_path', 'preview_4k_path',
            'additional_documentation_path'
        }
        
        clean_paths = {
            k: v for k, v in paths.items() 
            if k in valid_path_columns
        }
        
        if not clean_paths:
            return True  # Nic do aktualizacji
        
        return self.update(product_id, clean_paths)
    
    def update_file_metadata(
        self, 
        product_id: str, 
        file_type: str,
        filename: str = None,
        filesize: int = None,
        mimetype: str = None
    ) -> bool:
        """
        Zaktualizuj metadane pliku produktu.
        
        Args:
            product_id: UUID produktu
            file_type: Typ pliku ('cad_2d', 'cad_3d', 'user_image', etc.)
            filename: Oryginalna nazwa pliku
            filesize: Rozmiar w bajtach
            mimetype: MIME type
            
        Returns:
            True jeśli sukces
        """
        data = {}
        
        if filename is not None:
            data[f'{file_type}_filename'] = filename
        if filesize is not None:
            data[f'{file_type}_filesize'] = filesize
        if mimetype is not None:
            data[f'{file_type}_mimetype'] = mimetype
        
        if not data:
            return True
        
        return self.update(product_id, data)
    
    # =========================================================
    # DELETE
    # =========================================================
    
    def delete(self, product_id: str, hard: bool = False) -> bool:
        """
        Usuń produkt.
        
        Args:
            product_id: UUID produktu
            hard: True = trwałe usunięcie, False = soft delete (is_active=false)
            
        Returns:
            True jeśli sukces
        """
        try:
            if hard:
                # Najpierw usuń załączniki z bazy
                self.delete_all_attachments(product_id)
                
                # Trwale usuń produkt
                self.client.table(self.TABLE)\
                    .delete()\
                    .eq('id', product_id)\
                    .execute()
                
                print(f"[DB] ✅ Product hard deleted: {product_id}")
            else:
                # Soft delete
                self.update(product_id, {'is_active': False})
                print(f"[DB] ✅ Product soft deleted: {product_id}")
            
            return True
            
        except Exception as e:
            print(f"[DB] ❌ Delete product failed: {product_id} - {e}")
            return False
    
    def restore(self, product_id: str) -> bool:
        """
        Przywróć usunięty produkt (soft delete).
        
        Args:
            product_id: UUID produktu
            
        Returns:
            True jeśli sukces
        """
        return self.update(product_id, {'is_active': True})
    
    # =========================================================
    # ATTACHMENTS (tabela product_attachments)
    # =========================================================
    
    def create_attachment(self, data: Dict[str, Any]) -> Optional[str]:
        """
        Utwórz rekord załącznika.
        
        Args:
            data: Dane załącznika:
                - product_id (wymagane)
                - original_filename (wymagane)
                - storage_path (wymagane)
                - filesize (opcjonalne)
                - mimetype (opcjonalne)
                - sha256 (opcjonalne)
                - note (opcjonalne)
            
        Returns:
            UUID załącznika lub None
        """
        try:
            data['created_by'] = self._get_current_user()
            data['created_at'] = datetime.now().isoformat()
            data['is_active'] = True
            
            response = self.client.table(self.ATTACHMENTS_TABLE)\
                .insert(data)\
                .execute()
            
            if response.data and len(response.data) > 0:
                attachment_id = response.data[0].get('id')
                print(f"[DB] ✅ Attachment created: {attachment_id}")
                return attachment_id
            
            return None
            
        except Exception as e:
            print(f"[DB] ❌ Create attachment failed: {e}")
            return None
    
    def get_attachment(self, attachment_id: str) -> Optional[Dict]:
        """
        Pobierz załącznik po ID.
        
        Args:
            attachment_id: UUID załącznika
            
        Returns:
            Dane załącznika lub None
        """
        try:
            response = self.client.table(self.ATTACHMENTS_TABLE)\
                .select("*")\
                .eq('id', attachment_id)\
                .single()\
                .execute()
            
            return response.data if response.data else None
            
        except Exception as e:
            print(f"[DB] ❌ Get attachment failed: {attachment_id} - {e}")
            return None
    
    def get_attachments(
        self, 
        product_id: str, 
        active_only: bool = True
    ) -> List[Dict]:
        """
        Pobierz wszystkie załączniki produktu.
        
        Args:
            product_id: UUID produktu
            active_only: True = tylko aktywne załączniki
            
        Returns:
            Lista załączników
        """
        try:
            query = self.client.table(self.ATTACHMENTS_TABLE)\
                .select("*")\
                .eq('product_id', product_id)
            
            if active_only:
                query = query.eq('is_active', True)
            
            query = query.order('created_at', desc=True)
            
            response = query.execute()
            return response.data if response.data else []
            
        except Exception as e:
            print(f"[DB] ❌ Get attachments failed: {product_id} - {e}")
            return []
    
    def delete_attachment(self, attachment_id: str, hard: bool = False) -> bool:
        """
        Usuń załącznik.
        
        Args:
            attachment_id: UUID załącznika
            hard: True = trwałe usunięcie
            
        Returns:
            True jeśli sukces
        """
        try:
            if hard:
                self.client.table(self.ATTACHMENTS_TABLE)\
                    .delete()\
                    .eq('id', attachment_id)\
                    .execute()
            else:
                self.client.table(self.ATTACHMENTS_TABLE)\
                    .update({'is_active': False})\
                    .eq('id', attachment_id)\
                    .execute()
            
            return True
            
        except Exception as e:
            print(f"[DB] ❌ Delete attachment failed: {attachment_id} - {e}")
            return False
    
    def delete_all_attachments(self, product_id: str) -> int:
        """
        Usuń wszystkie załączniki produktu (hard delete).
        
        Args:
            product_id: UUID produktu
            
        Returns:
            Liczba usuniętych załączników
        """
        try:
            attachments = self.get_attachments(product_id, active_only=False)
            
            if attachments:
                self.client.table(self.ATTACHMENTS_TABLE)\
                    .delete()\
                    .eq('product_id', product_id)\
                    .execute()
            
            print(f"[DB] ✅ Deleted {len(attachments)} attachments for product {product_id}")
            return len(attachments)
            
        except Exception as e:
            print(f"[DB] ❌ Delete all attachments failed: {product_id} - {e}")
            return 0
    
    # =========================================================
    # HELPERS - Unikalne wartości do filtrów
    # =========================================================
    
    def get_unique_categories(self) -> List[str]:
        """Pobierz unikalne kategorie produktów (dla filtrów GUI)"""
        try:
            response = self.client.table(self.TABLE)\
                .select("category")\
                .eq('is_active', True)\
                .not_.is_('category', 'null')\
                .execute()
            
            categories = set(p['category'] for p in response.data if p.get('category'))
            return sorted(list(categories))
            
        except Exception:
            return []
    
    def get_unique_thicknesses(self) -> List[float]:
        """Pobierz unikalne grubości produktów (dla filtrów GUI)"""
        try:
            response = self.client.table(self.TABLE)\
                .select("thickness_mm")\
                .eq('is_active', True)\
                .not_.is_('thickness_mm', 'null')\
                .execute()
            
            thicknesses = set(p['thickness_mm'] for p in response.data if p.get('thickness_mm'))
            return sorted(list(thicknesses))
            
        except Exception:
            return []
    
    def get_unique_materials(self) -> List[Dict]:
        """Pobierz unikalne materiały (ID + nazwa)"""
        try:
            response = self.client.table('materials_dict')\
                .select("id, name")\
                .eq('is_active', True)\
                .order('name')\
                .execute()
            
            return response.data if response.data else []
            
        except Exception:
            return []
    
    # =========================================================
    # HELPERS - Generowanie kodów
    # =========================================================
    
    def generate_next_idx_code(self, prefix: str = "PC") -> str:
        """
        Generuj następny unikalny kod indeksowy.
        
        Format: {PREFIX}-{YYYYMM}-{NNNN}
        Przykład: PC-202411-0001
        
        Args:
            prefix: Prefix kodu (domyślnie "PC" = Product Code)
            
        Returns:
            Nowy unikalny kod indeksowy
        """
        year_month = datetime.now().strftime("%Y%m")
        pattern = f"{prefix}-{year_month}-%"
        
        try:
            response = self.client.table(self.TABLE)\
                .select("idx_code")\
                .like('idx_code', pattern)\
                .order('idx_code', desc=True)\
                .limit(1)\
                .execute()
            
            if response.data and len(response.data) > 0:
                last_code = response.data[0]['idx_code']
                last_number = int(last_code.split('-')[-1])
                next_number = last_number + 1
            else:
                next_number = 1
            
            return f"{prefix}-{year_month}-{next_number:04d}"
            
        except Exception as e:
            print(f"[DB] ⚠️ Generate idx_code failed: {e}")
            # Fallback - zwróć kod z timestamp
            import time
            return f"{prefix}-{year_month}-{int(time.time()) % 10000:04d}"
    
    def is_idx_code_unique(self, idx_code: str, exclude_id: str = None) -> bool:
        """
        Sprawdź czy kod indeksowy jest unikalny.
        
        Args:
            idx_code: Kod do sprawdzenia
            exclude_id: ID produktu do wykluczenia (przy edycji)
            
        Returns:
            True jeśli kod jest unikalny
        """
        try:
            query = self.client.table(self.TABLE)\
                .select("id")\
                .eq('idx_code', idx_code)
            
            if exclude_id:
                query = query.neq('id', exclude_id)
            
            response = query.execute()
            return len(response.data) == 0
            
        except Exception:
            return False
    
    # =========================================================
    # PRIVATE HELPERS
    # =========================================================
    
    def _get_current_user(self) -> str:
        """Pobierz nazwę bieżącego użytkownika systemowego"""
        try:
            return getpass.getuser()
        except Exception:
            return "system"


# =========================================================
# TESTY
# =========================================================

if __name__ == "__main__":
    print("ProductRepository - moduł dostępu do bazy danych")
    print("Użyj: repo = ProductRepository(get_supabase_client())")
