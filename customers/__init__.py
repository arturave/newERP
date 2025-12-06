"""
NewERP - Customers Module
=========================
Moduł zarządzania klientami (kontrahentami).
"""

from customers.repository import CustomerRepository
from customers.service import CustomerService

__all__ = [
    'CustomerRepository',
    'CustomerService',
]
