#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NewERP - Manufacturing System
Główny plik uruchomieniowy

Uruchomienie:
    python main.py              # Główny dashboard ERP
    python main.py --products   # Tylko okno produktów
    python main.py --customers  # Tylko okno klientów
    python main.py --pricing    # Zarządzanie cennikami
    python main.py --test       # Test połączenia
"""

import sys
import argparse
import logging
import customtkinter as ctk

from config.settings import CTK_APPEARANCE_MODE, CTK_COLOR_THEME, validate_config

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def setup_ctk():
    """Konfiguracja CustomTkinter"""
    ctk.set_appearance_mode(CTK_APPEARANCE_MODE)
    ctk.set_default_color_theme(CTK_COLOR_THEME)


def run_tests():
    """Uruchom testy połączenia"""
    import test_connection
    success = test_connection.run_all_tests()
    return 0 if success else 1


def run_dashboard():
    """Uruchom główny dashboard ERP"""
    setup_ctk()
    from main_dashboard import MainDashboard
    
    app = MainDashboard()
    app.mainloop()
    return 0


def run_products_window():
    """Uruchom okno produktów"""
    setup_ctk()
    from products.gui import ProductsWindow
    
    root = ctk.CTk()
    root.withdraw()
    
    window = ProductsWindow()
    
    def on_close():
        window.destroy()
        root.quit()
    
    window.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
    return 0


def run_customers_window():
    """Uruchom okno klientów"""
    setup_ctk()
    from core import get_supabase_client
    from customers.service import CustomerService
    from customers.gui import CustomersWindow
    
    root = ctk.CTk()
    root.withdraw()
    
    client = get_supabase_client()
    service = CustomerService(client)
    window = CustomersWindow(root, service)
    
    def on_close():
        window.destroy()
        root.quit()
    
    window.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
    return 0


def run_pricing_window():
    """Uruchom okno zarządzania cennikami"""
    setup_ctk()
    from pricing.gui import PricingWindow
    
    root = ctk.CTk()
    root.withdraw()
    
    window = PricingWindow()
    
    def on_close():
        window.destroy()
        root.quit()
    
    window.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
    return 0


def main():
    """Główna funkcja"""
    parser = argparse.ArgumentParser(description="NewERP Manufacturing System")
    parser.add_argument('--test', action='store_true', help='Uruchom testy połączenia')
    parser.add_argument('--products', action='store_true', help='Uruchom tylko okno produktów')
    parser.add_argument('--customers', action='store_true', help='Uruchom tylko okno klientów')
    parser.add_argument('--pricing', action='store_true', help='Uruchom zarządzanie cennikami')
    parser.add_argument('--debug', action='store_true', help='Tryb debug (więcej logów)')
    
    args = parser.parse_args()
    
    # Tryb debug
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Walidacja konfiguracji
    try:
        validate_config()
        logger.info("✓ Konfiguracja OK")
    except ValueError as e:
        print(f"❌ Błąd konfiguracji: {e}")
        print("\nSprawdź plik config/settings.py lub utwórz plik .env")
        return 1
    
    # Uruchom odpowiedni moduł
    if args.test:
        return run_tests()
    
    if args.products:
        return run_products_window()
    
    if args.customers:
        return run_customers_window()
    
    if args.pricing:
        return run_pricing_window()
    
    # Domyślnie - główny dashboard
    return run_dashboard()


if __name__ == "__main__":
    sys.exit(main())
