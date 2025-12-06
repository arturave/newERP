#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Products GUI Module - Interfejs użytkownika dla produktów

Komponenty:
- ProductsWindow: Główne okno listy produktów z filtrami
- ProductEditDialog: Dialog edycji/dodawania produktu

Użycie:
    from products.gui import ProductsWindow
    
    # Otwórz okno produktów
    window = ProductsWindow(parent)
    
    # Lub z callbackiem wyboru
    def on_select(product):
        print(f"Wybrano: {product['name']}")
    
    window = ProductsWindow(parent, on_product_selected=on_select)
"""

from products.gui.products_window import ProductsWindow
from products.gui.product_edit_dialog import ProductEditDialog

__all__ = [
    'ProductsWindow',
    'ProductEditDialog',
]
