"""
Document Renderer
=================
Wrapper na Jinja2 i WeasyPrint do renderowania dokumentow HTML i PDF.
"""

import os
import logging
from typing import Optional, Dict, Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .utils import format_currency, format_date_pl, number_to_text_pl

logger = logging.getLogger(__name__)


class DocumentRenderer:
    """
    Renderer dokumentow wykorzystujacy Jinja2 dla HTML i WeasyPrint dla PDF.

    Uzycie:
        renderer = DocumentRenderer()
        html = renderer.render_html("quotation.html", context_dict)
        pdf_bytes = renderer.render_pdf_bytes(html)
    """

    def __init__(self, templates_dir: str = None):
        """
        Inicjalizacja renderera.

        Args:
            templates_dir: Sciezka do katalogu z szablonami.
                          Domyslnie: documents/templates/
        """
        if not templates_dir:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            templates_dir = os.path.join(current_dir, "templates")

        self.templates_dir = templates_dir

        # Inicjalizacja srodowiska Jinja2
        self.env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )

        # Rejestracja filtrow Jinja2
        self._register_filters()

        logger.info(f"DocumentRenderer initialized with templates from: {templates_dir}")

    def _register_filters(self):
        """Rejestruje filtry Jinja2 dla szablonow"""
        self.env.filters['currency'] = format_currency
        self.env.filters['date_pl'] = format_date_pl
        self.env.filters['number_to_text'] = number_to_text_pl

        # Dodatkowe filtry
        self.env.filters['default'] = lambda v, d='': v if v else d

    def render_html(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        Renderuje szablon HTML z kontekstem.

        Args:
            template_name: Nazwa pliku szablonu (np. "quotation.html")
            context: Slownik z danymi do szablonu

        Returns:
            Wyrenderowany HTML jako string
        """
        try:
            template = self.env.get_template(template_name)
            html = template.render(**context)
            logger.debug(f"Rendered template: {template_name}")
            return html
        except Exception as e:
            logger.error(f"Error rendering template {template_name}: {e}")
            raise

    def render_html_from_string(self, template_content: str, context: Dict[str, Any]) -> str:
        """
        Renderuje szablon HTML z tekstu (dla szablonow z bazy danych).

        Args:
            template_content: Zawartosc szablonu Jinja2
            context: Slownik z danymi

        Returns:
            Wyrenderowany HTML
        """
        try:
            from jinja2 import Template
            template = self.env.from_string(template_content)
            return template.render(**context)
        except Exception as e:
            logger.error(f"Error rendering template from string: {e}")
            raise

    def render_pdf_bytes(self, html_content: str, css_content: str = None) -> bytes:
        """
        Konwertuje HTML na PDF.

        Args:
            html_content: HTML do konwersji
            css_content: Opcjonalny dodatkowy CSS

        Returns:
            PDF jako bytes
        """
        try:
            from weasyprint import HTML, CSS

            stylesheets = []
            if css_content:
                stylesheets.append(CSS(string=css_content))

            # base_url pozwala na relatywne sciezki w szablonach
            pdf_bytes = HTML(
                string=html_content,
                base_url=self.templates_dir
            ).write_pdf(stylesheets=stylesheets)

            logger.debug(f"Generated PDF: {len(pdf_bytes)} bytes")
            return pdf_bytes

        except ImportError:
            logger.error("WeasyPrint not installed. Install with: pip install weasyprint")
            logger.error("On Windows, GTK3 runtime is also required.")
            raise ImportError(
                "WeasyPrint not available. "
                "Install with: pip install weasyprint\n"
                "On Windows, install GTK3 runtime from: "
                "https://github.com/nickvidal/weasyprint/releases"
            )
        except Exception as e:
            logger.error(f"Error generating PDF: {e}")
            raise

    def render_document(
        self,
        template_name: str,
        context: Dict[str, Any],
        css_content: str = None,
        as_pdf: bool = True
    ) -> bytes | str:
        """
        Renderuje dokument (HTML lub PDF).

        Args:
            template_name: Nazwa szablonu
            context: Dane do szablonu
            css_content: Opcjonalny CSS
            as_pdf: True = zwroc PDF, False = zwroc HTML

        Returns:
            PDF bytes lub HTML string
        """
        html = self.render_html(template_name, context)

        if as_pdf:
            return self.render_pdf_bytes(html, css_content)
        return html

    def get_available_templates(self) -> list:
        """
        Zwraca liste dostepnych szablonow.

        Returns:
            Lista nazw plikow szablonow
        """
        templates = []
        if os.path.exists(self.templates_dir):
            for f in os.listdir(self.templates_dir):
                if f.endswith('.html'):
                    templates.append(f)
        return sorted(templates)

    def template_exists(self, template_name: str) -> bool:
        """Sprawdza czy szablon istnieje"""
        template_path = os.path.join(self.templates_dir, template_name)
        return os.path.exists(template_path)


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    print("Testing DocumentRenderer...")

    renderer = DocumentRenderer()

    # Lista szablonow
    templates = renderer.get_available_templates()
    print(f"Available templates: {templates}")

    # Test kontekstu
    from datetime import date
    from decimal import Decimal

    test_context = {
        'doc_type': 'QUOTATION',
        'doc_type_label': 'OFERTA HANDLOWA',
        'doc_number': 'QUOTATION/2025/000001',
        'issue_date': date.today().strftime('%Y-%m-%d'),
        'place': 'Warszawa',
        'seller': {
            'name': 'Firma Testowa Sp. z o.o.',
            'address': 'ul. Testowa 1, 00-001 Warszawa',
            'nip': '123-456-78-90',
        },
        'buyer': {
            'name': 'Klient Testowy',
            'address': 'ul. Kliencka 2, 00-002 Krakow',
            'nip': '987-654-32-10',
        },
        'items': [
            {'position': 1, 'name': 'Produkt A', 'quantity': 10, 'unit': 'szt', 'price_net': 100.0, 'value_net': 1000.0},
            {'position': 2, 'name': 'Produkt B', 'quantity': 5, 'unit': 'szt', 'price_net': 200.0, 'value_net': 1000.0},
        ],
        'total_net': 2000.0,
        'total_vat': 460.0,
        'total_gross': 2460.0,
        'currency': 'PLN',
    }

    # Test renderowania HTML (jesli szablon istnieje)
    if renderer.template_exists('quotation.html'):
        html = renderer.render_html('quotation.html', test_context)
        print(f"HTML rendered: {len(html)} chars")
    else:
        print("Template quotation.html not found - skipping HTML test")

    print("\nDocumentRenderer test completed!")
