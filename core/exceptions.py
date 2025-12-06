"""
NewERP - Własne wyjątki
=======================
Hierarchia wyjątków dla całego systemu.
"""


class NewERPError(Exception):
    """Bazowy wyjątek dla wszystkich błędów NewERP"""
    
    def __init__(self, message: str, code: str = None, details: dict = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}
    
    def __str__(self):
        if self.details:
            return f"[{self.code}] {self.message} | Details: {self.details}"
        return f"[{self.code}] {self.message}"


# ============================================================
# Database Errors
# ============================================================

class DatabaseError(NewERPError):
    """Błędy związane z bazą danych"""
    pass


class RecordNotFoundError(DatabaseError):
    """Rekord nie został znaleziony"""
    
    def __init__(self, entity_type: str, entity_id: str):
        super().__init__(
            f"{entity_type} with id '{entity_id}' not found",
            code="RECORD_NOT_FOUND",
            details={"entity_type": entity_type, "entity_id": entity_id}
        )


class DuplicateRecordError(DatabaseError):
    """Próba utworzenia duplikatu (unique constraint)"""
    
    def __init__(self, entity_type: str, field: str, value: str):
        super().__init__(
            f"{entity_type} with {field}='{value}' already exists",
            code="DUPLICATE_RECORD",
            details={"entity_type": entity_type, "field": field, "value": value}
        )


class OptimisticLockError(DatabaseError):
    """Konflikt wersji przy aktualizacji (optimistic locking)"""
    
    def __init__(self, entity_type: str, entity_id: str, expected_version: int):
        super().__init__(
            f"{entity_type} '{entity_id}' was modified by another user. "
            f"Expected version {expected_version}.",
            code="OPTIMISTIC_LOCK_ERROR",
            details={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "expected_version": expected_version
            }
        )


class ForeignKeyError(DatabaseError):
    """Naruszenie klucza obcego"""
    
    def __init__(self, entity_type: str, referenced_type: str, referenced_id: str):
        super().__init__(
            f"Cannot delete/update {entity_type}: referenced by {referenced_type}",
            code="FOREIGN_KEY_ERROR",
            details={
                "entity_type": entity_type,
                "referenced_type": referenced_type,
                "referenced_id": referenced_id
            }
        )


# ============================================================
# Storage Errors
# ============================================================

class StorageError(NewERPError):
    """Błędy związane z Supabase Storage"""
    pass


class FileNotFoundError(StorageError):
    """Plik nie został znaleziony w Storage"""
    
    def __init__(self, path: str):
        super().__init__(
            f"File not found: {path}",
            code="FILE_NOT_FOUND",
            details={"path": path}
        )


class FileUploadError(StorageError):
    """Błąd podczas uploadu pliku"""
    
    def __init__(self, path: str, reason: str = None):
        super().__init__(
            f"Failed to upload file: {path}" + (f" - {reason}" if reason else ""),
            code="FILE_UPLOAD_ERROR",
            details={"path": path, "reason": reason}
        )


class FileDownloadError(StorageError):
    """Błąd podczas pobierania pliku"""
    
    def __init__(self, path: str, reason: str = None):
        super().__init__(
            f"Failed to download file: {path}" + (f" - {reason}" if reason else ""),
            code="FILE_DOWNLOAD_ERROR",
            details={"path": path, "reason": reason}
        )


class FileTooLargeError(StorageError):
    """Plik jest za duży"""
    
    def __init__(self, filename: str, size_mb: float, max_size_mb: float):
        super().__init__(
            f"File '{filename}' is too large ({size_mb:.1f} MB). Maximum: {max_size_mb:.1f} MB",
            code="FILE_TOO_LARGE",
            details={
                "filename": filename,
                "size_mb": size_mb,
                "max_size_mb": max_size_mb
            }
        )


class InvalidFileTypeError(StorageError):
    """Nieprawidłowy typ pliku"""
    
    def __init__(self, filename: str, allowed_types: list):
        super().__init__(
            f"Invalid file type: '{filename}'. Allowed: {', '.join(allowed_types)}",
            code="INVALID_FILE_TYPE",
            details={"filename": filename, "allowed_types": allowed_types}
        )


# ============================================================
# Validation Errors
# ============================================================

class ValidationError(NewERPError):
    """Błędy walidacji danych"""
    pass


class RequiredFieldError(ValidationError):
    """Brak wymaganego pola"""
    
    def __init__(self, field: str, entity_type: str = None):
        msg = f"Field '{field}' is required"
        if entity_type:
            msg = f"{entity_type}: {msg}"
        super().__init__(msg, code="REQUIRED_FIELD", details={"field": field})


class InvalidFieldValueError(ValidationError):
    """Nieprawidłowa wartość pola"""
    
    def __init__(self, field: str, value, reason: str = None):
        msg = f"Invalid value for field '{field}': {value}"
        if reason:
            msg += f" - {reason}"
        super().__init__(
            msg,
            code="INVALID_FIELD_VALUE",
            details={"field": field, "value": str(value), "reason": reason}
        )


class BusinessRuleError(ValidationError):
    """Naruszenie reguły biznesowej"""
    
    def __init__(self, rule: str, details: dict = None):
        super().__init__(
            f"Business rule violation: {rule}",
            code="BUSINESS_RULE_ERROR",
            details=details or {}
        )


# ============================================================
# Workflow Errors
# ============================================================

class WorkflowError(NewERPError):
    """Błędy związane z workflow/state machine"""
    pass


class InvalidStateTransitionError(WorkflowError):
    """Nieprawidłowe przejście między stanami"""
    
    def __init__(self, entity_type: str, current_state: str, target_state: str):
        super().__init__(
            f"Cannot transition {entity_type} from '{current_state}' to '{target_state}'",
            code="INVALID_STATE_TRANSITION",
            details={
                "entity_type": entity_type,
                "current_state": current_state,
                "target_state": target_state
            }
        )


class ActionNotAllowedError(WorkflowError):
    """Akcja niedozwolona w obecnym stanie"""
    
    def __init__(self, action: str, current_state: str, entity_type: str = None):
        msg = f"Action '{action}' not allowed in state '{current_state}'"
        if entity_type:
            msg = f"{entity_type}: {msg}"
        super().__init__(
            msg,
            code="ACTION_NOT_ALLOWED",
            details={
                "action": action,
                "current_state": current_state,
                "entity_type": entity_type
            }
        )


# ============================================================
# Authentication/Authorization Errors
# ============================================================

class AuthError(NewERPError):
    """Błędy autentykacji/autoryzacji"""
    pass


class NotAuthenticatedError(AuthError):
    """Użytkownik nie jest zalogowany"""
    
    def __init__(self):
        super().__init__(
            "User is not authenticated",
            code="NOT_AUTHENTICATED"
        )


class PermissionDeniedError(AuthError):
    """Brak uprawnień do operacji"""
    
    def __init__(self, action: str, resource: str = None):
        msg = f"Permission denied: {action}"
        if resource:
            msg += f" on {resource}"
        super().__init__(msg, code="PERMISSION_DENIED")


# ============================================================
# Integration Errors
# ============================================================

class IntegrationError(NewERPError):
    """Błędy integracji z zewnętrznymi systemami"""
    pass


class SupabaseConnectionError(IntegrationError):
    """Błąd połączenia z Supabase"""
    
    def __init__(self, reason: str = None):
        super().__init__(
            "Failed to connect to Supabase" + (f": {reason}" if reason else ""),
            code="SUPABASE_CONNECTION_ERROR"
        )


class ExternalServiceError(IntegrationError):
    """Błąd zewnętrznego serwisu"""
    
    def __init__(self, service: str, reason: str = None):
        super().__init__(
            f"External service error ({service})" + (f": {reason}" if reason else ""),
            code="EXTERNAL_SERVICE_ERROR",
            details={"service": service, "reason": reason}
        )
