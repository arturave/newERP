"""
NewERP - Audit Trail
====================
System logowania zmian w systemie.
Kto, kiedy, co zmienił - pełna historia.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from enum import Enum
import json
import logging

from supabase import Client

logger = logging.getLogger(__name__)


class AuditAction(Enum):
    """Typy akcji do audytu"""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    RESTORE = "restore"
    STATUS_CHANGE = "status_change"
    FILE_UPLOAD = "file_upload"
    FILE_DELETE = "file_delete"
    LOGIN = "login"
    LOGOUT = "logout"
    EXPORT = "export"
    IMPORT = "import"


@dataclass
class AuditEntry:
    """Wpis w dzienniku audytu"""
    entity_type: str
    entity_id: str
    action: AuditAction
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    changed_fields: Optional[List[str]] = None
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    correlation_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        
        # Auto-wykryj zmienione pola
        if self.changed_fields is None and self.old_values and self.new_values:
            self.changed_fields = self._detect_changed_fields()
    
    def _detect_changed_fields(self) -> List[str]:
        """Wykryj które pola się zmieniły"""
        if not self.old_values or not self.new_values:
            return []
        
        changed = []
        all_keys = set(self.old_values.keys()) | set(self.new_values.keys())
        
        for key in all_keys:
            old_val = self.old_values.get(key)
            new_val = self.new_values.get(key)
            if old_val != new_val:
                changed.append(key)
        
        return changed
    
    def to_dict(self) -> dict:
        """Konwersja do słownika (do zapisu w DB)"""
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "action": self.action.value,
            "old_values": self.old_values,
            "new_values": self.new_values,
            "changed_fields": self.changed_fields,
            "user_id": self.user_id,
            "user_email": self.user_email,
            "correlation_id": self.correlation_id,
            "metadata": self.metadata,
            "created_at": self.timestamp.isoformat()
        }


class AuditService:
    """
    Serwis do zarządzania audytem.
    
    Usage:
        audit = AuditService(supabase_client)
        
        # Loguj utworzenie
        audit.log_create("product", product_id, product_data, user_id="user123")
        
        # Loguj aktualizację
        audit.log_update("product", product_id, old_data, new_data)
        
        # Pobierz historię
        history = audit.get_history("product", product_id)
    """
    
    TABLE_NAME = "audit_log"
    
    # Pola do wykluczenia z audytu (wrażliwe lub zbędne)
    EXCLUDED_FIELDS: Set[str] = {
        "password",
        "password_hash",
        "token",
        "api_key",
        "secret",
        "updated_at",  # zawsze się zmienia, nie ma sensu logować
    }
    
    def __init__(self, client: Client, default_user_id: str = None):
        self.client = client
        self.default_user_id = default_user_id
        self._enabled = True
    
    def enable(self):
        """Włącz audyt"""
        self._enabled = True
    
    def disable(self):
        """Wyłącz audyt (np. przy migracji)"""
        self._enabled = False
    
    def log(
        self,
        entity_type: str,
        entity_id: str,
        action: AuditAction,
        old_values: dict = None,
        new_values: dict = None,
        user_id: str = None,
        user_email: str = None,
        correlation_id: str = None,
        metadata: dict = None
    ) -> Optional[str]:
        """
        Zapisz wpis audytu.
        
        Returns:
            ID wpisu audytu lub None jeśli audyt wyłączony
        """
        if not self._enabled:
            return None
        
        # Filtruj wrażliwe pola
        if old_values:
            old_values = self._filter_sensitive(old_values)
        if new_values:
            new_values = self._filter_sensitive(new_values)
        
        entry = AuditEntry(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            old_values=old_values,
            new_values=new_values,
            user_id=user_id or self.default_user_id,
            user_email=user_email,
            correlation_id=correlation_id,
            metadata=metadata
        )
        
        try:
            response = self.client.table(self.TABLE_NAME)\
                .insert(entry.to_dict())\
                .execute()
            
            if response.data:
                audit_id = response.data[0].get('id')
                logger.debug(
                    f"[Audit] {action.value.upper()} {entity_type}/{entity_id} "
                    f"| User: {user_id or 'system'}"
                )
                return audit_id
            
        except Exception as e:
            # Audyt nie powinien blokować głównej operacji
            logger.error(f"[Audit] Failed to log: {e}")
            return None
    
    def _filter_sensitive(self, data: dict) -> dict:
        """Usuń wrażliwe pola z danych"""
        return {
            k: v for k, v in data.items() 
            if k.lower() not in self.EXCLUDED_FIELDS
        }
    
    # ============================================================
    # Convenience Methods
    # ============================================================
    
    def log_create(
        self,
        entity_type: str,
        entity_id: str,
        data: dict,
        user_id: str = None,
        **kwargs
    ) -> Optional[str]:
        """Loguj utworzenie encji"""
        return self.log(
            entity_type=entity_type,
            entity_id=entity_id,
            action=AuditAction.CREATE,
            new_values=data,
            user_id=user_id,
            **kwargs
        )
    
    def log_update(
        self,
        entity_type: str,
        entity_id: str,
        old_data: dict,
        new_data: dict,
        user_id: str = None,
        **kwargs
    ) -> Optional[str]:
        """Loguj aktualizację encji"""
        return self.log(
            entity_type=entity_type,
            entity_id=entity_id,
            action=AuditAction.UPDATE,
            old_values=old_data,
            new_values=new_data,
            user_id=user_id,
            **kwargs
        )
    
    def log_delete(
        self,
        entity_type: str,
        entity_id: str,
        data: dict,
        user_id: str = None,
        **kwargs
    ) -> Optional[str]:
        """Loguj usunięcie encji"""
        return self.log(
            entity_type=entity_type,
            entity_id=entity_id,
            action=AuditAction.DELETE,
            old_values=data,
            user_id=user_id,
            **kwargs
        )
    
    def log_restore(
        self,
        entity_type: str,
        entity_id: str,
        user_id: str = None,
        **kwargs
    ) -> Optional[str]:
        """Loguj przywrócenie encji"""
        return self.log(
            entity_type=entity_type,
            entity_id=entity_id,
            action=AuditAction.RESTORE,
            user_id=user_id,
            **kwargs
        )
    
    def log_status_change(
        self,
        entity_type: str,
        entity_id: str,
        old_status: str,
        new_status: str,
        user_id: str = None,
        **kwargs
    ) -> Optional[str]:
        """Loguj zmianę statusu"""
        return self.log(
            entity_type=entity_type,
            entity_id=entity_id,
            action=AuditAction.STATUS_CHANGE,
            old_values={"status": old_status},
            new_values={"status": new_status},
            user_id=user_id,
            **kwargs
        )
    
    def log_file_upload(
        self,
        entity_type: str,
        entity_id: str,
        filename: str,
        file_path: str,
        user_id: str = None,
        **kwargs
    ) -> Optional[str]:
        """Loguj upload pliku"""
        return self.log(
            entity_type=entity_type,
            entity_id=entity_id,
            action=AuditAction.FILE_UPLOAD,
            new_values={"filename": filename, "path": file_path},
            user_id=user_id,
            **kwargs
        )
    
    def log_file_delete(
        self,
        entity_type: str,
        entity_id: str,
        filename: str,
        file_path: str,
        user_id: str = None,
        **kwargs
    ) -> Optional[str]:
        """Loguj usunięcie pliku"""
        return self.log(
            entity_type=entity_type,
            entity_id=entity_id,
            action=AuditAction.FILE_DELETE,
            old_values={"filename": filename, "path": file_path},
            user_id=user_id,
            **kwargs
        )
    
    # ============================================================
    # Query Methods
    # ============================================================
    
    def get_history(
        self,
        entity_type: str,
        entity_id: str,
        limit: int = 100
    ) -> List[dict]:
        """
        Pobierz historię zmian dla encji.
        
        Returns:
            Lista wpisów audytu (najnowsze pierwsze)
        """
        try:
            response = self.client.table(self.TABLE_NAME)\
                .select('*')\
                .eq('entity_type', entity_type)\
                .eq('entity_id', entity_id)\
                .order('created_at', desc=True)\
                .limit(limit)\
                .execute()
            
            return response.data or []
            
        except Exception as e:
            logger.error(f"[Audit] Failed to get history: {e}")
            return []
    
    def get_by_user(
        self,
        user_id: str,
        limit: int = 100,
        entity_type: str = None
    ) -> List[dict]:
        """Pobierz akcje użytkownika"""
        try:
            query = self.client.table(self.TABLE_NAME)\
                .select('*')\
                .eq('user_id', user_id)\
                .order('created_at', desc=True)\
                .limit(limit)
            
            if entity_type:
                query = query.eq('entity_type', entity_type)
            
            response = query.execute()
            return response.data or []
            
        except Exception as e:
            logger.error(f"[Audit] Failed to get user history: {e}")
            return []
    
    def get_by_correlation(self, correlation_id: str) -> List[dict]:
        """Pobierz wszystkie powiązane akcje (np. z jednej transakcji)"""
        try:
            response = self.client.table(self.TABLE_NAME)\
                .select('*')\
                .eq('correlation_id', correlation_id)\
                .order('created_at', desc=False)\
                .execute()
            
            return response.data or []
            
        except Exception as e:
            logger.error(f"[Audit] Failed to get by correlation: {e}")
            return []
    
    def get_recent(
        self,
        limit: int = 50,
        entity_type: str = None,
        action: AuditAction = None
    ) -> List[dict]:
        """Pobierz ostatnie akcje w systemie"""
        try:
            query = self.client.table(self.TABLE_NAME)\
                .select('*')\
                .order('created_at', desc=True)\
                .limit(limit)
            
            if entity_type:
                query = query.eq('entity_type', entity_type)
            
            if action:
                query = query.eq('action', action.value)
            
            response = query.execute()
            return response.data or []
            
        except Exception as e:
            logger.error(f"[Audit] Failed to get recent: {e}")
            return []
    
    def search(
        self,
        entity_type: str = None,
        entity_id: str = None,
        user_id: str = None,
        action: AuditAction = None,
        date_from: str = None,
        date_to: str = None,
        limit: int = 100
    ) -> List[dict]:
        """Wyszukaj wpisy audytu z filtrami"""
        try:
            query = self.client.table(self.TABLE_NAME)\
                .select('*')\
                .order('created_at', desc=True)\
                .limit(limit)
            
            if entity_type:
                query = query.eq('entity_type', entity_type)
            if entity_id:
                query = query.eq('entity_id', entity_id)
            if user_id:
                query = query.eq('user_id', user_id)
            if action:
                query = query.eq('action', action.value)
            if date_from:
                query = query.gte('created_at', date_from)
            if date_to:
                query = query.lte('created_at', date_to)
            
            response = query.execute()
            return response.data or []
            
        except Exception as e:
            logger.error(f"[Audit] Search failed: {e}")
            return []


# ============================================================
# Utility Functions
# ============================================================

def diff_dicts(old: dict, new: dict) -> Dict[str, dict]:
    """
    Porównaj dwa słowniki i zwróć różnice.
    
    Returns:
        {
            "added": {"field": value},
            "removed": {"field": value},
            "changed": {"field": {"old": old_val, "new": new_val}}
        }
    """
    old = old or {}
    new = new or {}
    
    all_keys = set(old.keys()) | set(new.keys())
    
    result = {
        "added": {},
        "removed": {},
        "changed": {}
    }
    
    for key in all_keys:
        old_val = old.get(key)
        new_val = new.get(key)
        
        if key not in old:
            result["added"][key] = new_val
        elif key not in new:
            result["removed"][key] = old_val
        elif old_val != new_val:
            result["changed"][key] = {"old": old_val, "new": new_val}
    
    return result


def format_audit_entry(entry: dict) -> str:
    """Sformatuj wpis audytu do wyświetlenia"""
    action = entry.get('action', 'unknown')
    entity = f"{entry.get('entity_type', '?')}/{entry.get('entity_id', '?')[:8]}"
    user = entry.get('user_email') or entry.get('user_id', 'system')
    timestamp = entry.get('created_at', '')[:19]
    
    # Opis zmian
    changed = entry.get('changed_fields', [])
    if changed:
        changes = f"Changed: {', '.join(changed)}"
    else:
        changes = ""
    
    return f"[{timestamp}] {action.upper()} {entity} by {user} {changes}"
