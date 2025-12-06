#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NewERP Core Module
==================
Wspólne komponenty dla wszystkich modułów.
"""

# Supabase client
from core.supabase_client import (
    get_supabase_client,
    reset_client,
    test_connection,
    ensure_authenticated,
    get_auth_client
)

# Exceptions
from core.exceptions import (
    NewERPError,
    DatabaseError,
    RecordNotFoundError,
    DuplicateRecordError,
    OptimisticLockError,
    ForeignKeyError,
    StorageError,
    FileUploadError,
    FileDownloadError,
    FileTooLargeError,
    InvalidFileTypeError,
    ValidationError,
    RequiredFieldError,
    InvalidFieldValueError,
    BusinessRuleError,
    WorkflowError,
    InvalidStateTransitionError,
    ActionNotAllowedError,
    AuthError,
    NotAuthenticatedError,
    PermissionDeniedError,
    IntegrationError,
    SupabaseConnectionError,
    ExternalServiceError,
)

# Events
from core.events import (
    EventType,
    Event,
    EventBus,
    EventHandler,
    create_event,
    get_event_bus,
    on_event,
    on_all_events,
    setup_event_logging,
)

# Filters / Query Builder
from core.filters import (
    FilterOperator,
    Filter,
    Sort,
    Pagination,
    QueryParams,
    QueryBuilder,
    create_query_params,
    parse_sort_string,
    parse_filter_string,
    CommonFilters,
)

# Audit
from core.audit import (
    AuditAction,
    AuditEntry,
    AuditService,
    diff_dicts,
    format_audit_entry,
)

# Base classes
from core.base_repository import BaseRepository
from core.base_service import BaseService, ServiceRegistry


__all__ = [
    # Supabase Client
    'get_supabase_client',
    'reset_client', 
    'test_connection',
    'ensure_authenticated',
    'get_auth_client',
    
    # Exceptions
    'NewERPError',
    'DatabaseError',
    'RecordNotFoundError',
    'DuplicateRecordError',
    'OptimisticLockError',
    'ForeignKeyError',
    'StorageError',
    'FileUploadError',
    'FileDownloadError',
    'FileTooLargeError',
    'InvalidFileTypeError',
    'ValidationError',
    'RequiredFieldError',
    'InvalidFieldValueError',
    'BusinessRuleError',
    'WorkflowError',
    'InvalidStateTransitionError',
    'ActionNotAllowedError',
    'AuthError',
    'NotAuthenticatedError',
    'PermissionDeniedError',
    'IntegrationError',
    'SupabaseConnectionError',
    'ExternalServiceError',
    
    # Events
    'EventType',
    'Event',
    'EventBus',
    'EventHandler',
    'create_event',
    'get_event_bus',
    'on_event',
    'on_all_events',
    'setup_event_logging',
    
    # Filters
    'FilterOperator',
    'Filter',
    'Sort',
    'Pagination',
    'QueryParams',
    'QueryBuilder',
    'create_query_params',
    'parse_sort_string',
    'parse_filter_string',
    'CommonFilters',
    
    # Audit
    'AuditAction',
    'AuditEntry',
    'AuditService',
    'diff_dicts',
    'format_audit_entry',
    
    # Base classes
    'BaseRepository',
    'BaseService',
    'ServiceRegistry',
]
