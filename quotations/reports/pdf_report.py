"""
PDF Report Generator
====================
Generowanie profesjonalnych raportów PDF z wycen i nestingu.

Wymaga: pip install reportlab
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple
import io

logger = logging.getLogger(__name__)

# Sprawdź dostępność reportlab
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm, cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, Image as RLImage, HRFlowable
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False
    logger.warning("reportlab not installed. PDF reports unavailable. Run: pip install reportlab")

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


from . import QuotationReport, ReportGenerator, NestingReport, SheetReport


class PDFReportGenerator(ReportGenerator):
    """Generator raportów PDF"""
    
    # Kolory firmowe
    COLOR_PRIMARY = colors.HexColor('#8b5cf6')  # Fioletowy
    COLOR_SECONDARY = colors.HexColor('#6366f1')
    COLOR_DARK = colors.HexColor('#1a1a1a')
    COLOR_GRAY = colors.HexColor('#666666')
    COLOR_LIGHT_GRAY = colors.HexColor('#f3f4f6')
    COLOR_SUCCESS = colors.HexColor('#22c55e')
    COLOR_WARNING = colors.HexColor('#f59e0b')
    
    def __init__(self, report: QuotationReport):
        super().__init__(report)
        self.styles = None
        self.elements = []
        
        if HAS_REPORTLAB:
            self._setup_styles()
    
    def _setup_styles(self):
        """Konfiguruj style dokumentu"""
        self.styles = getSampleStyleSheet()
        
        # Tytuł główny
        self.styles.add(ParagraphStyle(
            name='MainTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=self.COLOR_PRIMARY,
            spaceAfter=20,
            alignment=TA_CENTER
        ))
        
        # Nagłówek sekcji
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=self.COLOR_DARK,
            spaceBefore=15,
            spaceAfter=10,
            borderPadding=5,
            backColor=self.COLOR_LIGHT_GRAY
        ))
        
        # Podtytuł
        self.styles.add(ParagraphStyle(
            name='SubHeader',
            parent=self.styles['Heading3'],
            fontSize=11,
            textColor=self.COLOR_GRAY,
            spaceBefore=10,
            spaceAfter=5
        ))
        
        # Normalny tekst
        self.styles.add(ParagraphStyle(
            name='NormalText',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=self.COLOR_DARK,
            spaceAfter=5
        ))
        
        # Mały tekst
        self.styles.add(ParagraphStyle(
            name='SmallText',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=self.COLOR_GRAY
        ))
        
        # Tekst prawostronny
        self.styles.add(ParagraphStyle(
            name='RightText',
            parent=self.styles['Normal'],
            fontSize=10,
            alignment=TA_RIGHT
        ))
        
        # Suma
        self.styles.add(ParagraphStyle(
            name='TotalText',
            parent=self.styles['Normal'],
            fontSize=14,
            textColor=self.COLOR_PRIMARY,
            fontName='Helvetica-Bold',
            alignment=TA_RIGHT
        ))
    
    def generate(self, output_path: str) -> bool:
        """Generuj raport PDF"""
        if not HAS_REPORTLAB:
            logger.error("reportlab not installed")
            return False
        
        try:
            # Utwórz dokument
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                rightMargin=20*mm,
                leftMargin=20*mm,
                topMargin=20*mm,
                bottomMargin=20*mm
            )
            
            self.elements = []
            
            # Buduj zawartość
            self._add_header()
            self._add_customer_info()
            self._add_parts_table()
            self._add_nesting_summary()
            self._add_cost_breakdown()
            self._add_footer()
            
            # Generuj PDF
            doc.build(self.elements)
            
            logger.info(f"PDF report generated: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"PDF generation error: {e}")
            return False
    
    def _add_header(self):
        """Dodaj nagłówek dokumentu"""
        # Tytuł
        self.elements.append(Paragraph(
            "WYCENA / QUOTATION",
            self.styles['MainTitle']
        ))
        
        # Numer i data
        header_data = [
            [f"Nr wyceny: {self.report.quotation_id or 'DRAFT'}",
             f"Data: {self._format_date(self.report.quotation_date)}"],
            [f"Algorytm: {self.report.algorithm}",
             f"Ważna do: {self._format_date(self.report.valid_until) or 'N/A'}"]
        ]
        
        header_table = Table(header_data, colWidths=[250, 250])
        header_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), self.COLOR_GRAY),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ]))
        
        self.elements.append(header_table)
        self.elements.append(Spacer(1, 10*mm))
    
    def _add_customer_info(self):
        """Dodaj informacje o kliencie"""
        self.elements.append(Paragraph("📋 DANE KLIENTA", self.styles['SectionHeader']))
        
        customer_lines = []
        if self.report.customer_company:
            customer_lines.append(f"<b>{self.report.customer_company}</b>")
        if self.report.customer_name:
            customer_lines.append(self.report.customer_name)
        if self.report.customer_address:
            customer_lines.append(self.report.customer_address)
        if self.report.customer_nip:
            customer_lines.append(f"NIP: {self.report.customer_nip}")
        if self.report.customer_email:
            customer_lines.append(f"Email: {self.report.customer_email}")
        if self.report.customer_phone:
            customer_lines.append(f"Tel: {self.report.customer_phone}")
        
        if customer_lines:
            for line in customer_lines:
                self.elements.append(Paragraph(line, self.styles['NormalText']))
        else:
            self.elements.append(Paragraph("(Brak danych klienta)", self.styles['SmallText']))
        
        self.elements.append(Spacer(1, 5*mm))
    
    def _add_parts_table(self):
        """Dodaj tabelę detali"""
        self.elements.append(Paragraph("📦 SPECYFIKACJA DETALI", self.styles['SectionHeader']))
        
        # Podsumowanie
        summary_text = (
            f"Liczba pozycji: <b>{len(self.report.parts)}</b> | "
            f"Łączna ilość: <b>{self.report.total_parts_count}</b> szt. | "
            f"Materiały: <b>{', '.join(self.report.unique_materials)}</b>"
        )
        self.elements.append(Paragraph(summary_text, self.styles['NormalText']))
        self.elements.append(Spacer(1, 3*mm))
        
        # Tabela detali
        table_data = [
            ['Lp.', 'Nazwa detalu', 'Materiał', 'Grubość', 'Wymiary [mm]', 'Ilość', 'Gięcie', 'Cena jedn.', 'Wartość']
        ]
        
        for i, part in enumerate(self.report.parts, 1):
            table_data.append([
                str(i),
                part.name[:30] + ('...' if len(part.name) > 30 else ''),
                part.material,
                f"{part.thickness_mm}mm",
                f"{part.width_mm:.0f}x{part.height_mm:.0f}",
                str(part.quantity),
                "Tak" if part.has_bending else "-",
                self._format_currency(part.unit_cost) if part.unit_cost else "-",
                self._format_currency(part.total_cost) if part.total_cost else "-"
            ])
        
        # Szerokości kolumn
        col_widths = [25, 100, 55, 40, 60, 35, 35, 60, 60]
        
        parts_table = Table(table_data, colWidths=col_widths, repeatRows=1)
        parts_table.setStyle(TableStyle([
            # Nagłówek
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            
            # Dane
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # Lp
            ('ALIGN', (3, 1), (6, -1), 'CENTER'),  # Grubość, wymiary, ilość, gięcie
            ('ALIGN', (7, 1), (-1, -1), 'RIGHT'),  # Ceny
            
            # Obramowanie
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRAY),
            
            # Alternatywne wiersze
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.COLOR_LIGHT_GRAY]),
            
            # Padding
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        
        self.elements.append(parts_table)
        self.elements.append(Spacer(1, 5*mm))
    
    def _add_nesting_summary(self):
        """Dodaj podsumowanie nestingu"""
        if not self.report.nesting:
            return
        
        self.elements.append(Paragraph("📐 WYNIKI NESTINGU", self.styles['SectionHeader']))
        
        nesting = self.report.nesting
        
        # Statystyki główne
        stats_data = [
            ['Parametr', 'Wartość'],
            ['Liczba arkuszy', str(nesting.total_sheets)],
            ['Umieszczone detale', str(nesting.total_parts)],
            ['Średnie wykorzystanie', self._format_percent(nesting.average_utilization)],
            ['Całkowita powierzchnia arkuszy', self._format_area(nesting.total_sheet_area_mm2)],
            ['Wykorzystana powierzchnia', self._format_area(nesting.total_used_area_mm2)],
            ['Odpad', self._format_area(nesting.total_waste_area_mm2)],
        ]
        
        stats_table = Table(stats_data, colWidths=[200, 150])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_SECONDARY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRAY),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.COLOR_LIGHT_GRAY]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        
        self.elements.append(stats_table)
        self.elements.append(Spacer(1, 3*mm))
        
        # Parametry nestingu
        params_text = (
            f"Kerf: {self.report.kerf_width}mm | "
            f"Odstęp: {self.report.part_spacing}mm | "
            f"Margines: {self.report.sheet_margin}mm"
        )
        self.elements.append(Paragraph(params_text, self.styles['SmallText']))
        
        # Szczegóły arkuszy
        if nesting.sheets:
            self.elements.append(Spacer(1, 3*mm))
            self.elements.append(Paragraph("Szczegóły arkuszy:", self.styles['SubHeader']))
            
            sheets_data = [['Nr', 'Format', 'Materiał', 'Grubość', 'Detali', 'Wykorzystanie']]
            
            for sheet in nesting.sheets:
                sheets_data.append([
                    str(sheet.index),
                    sheet.format_name,
                    sheet.material,
                    f"{sheet.thickness_mm}mm",
                    str(sheet.parts_count),
                    self._format_percent(sheet.utilization)
                ])
            
            sheets_table = Table(sheets_data, colWidths=[30, 100, 80, 50, 50, 80])
            sheets_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_GRAY),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRAY),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            
            self.elements.append(sheets_table)
        
        self.elements.append(Spacer(1, 5*mm))
    
    def _add_cost_breakdown(self):
        """Dodaj rozbicie kosztów"""
        self.elements.append(Paragraph("💰 KALKULACJA KOSZTÓW", self.styles['SectionHeader']))
        
        costs = self.report.costs
        
        cost_data = [
            ['Pozycja', 'Wartość'],
            ['Materiał', self._format_currency(costs.material_cost)],
            ['Cięcie laserowe', self._format_currency(costs.cutting_cost)],
            ['Gięcie', self._format_currency(costs.bending_cost)],
            ['Przygotowanie (setup)', self._format_currency(costs.setup_cost)],
            ['Programowanie', self._format_currency(costs.programming_cost)],
        ]
        
        if costs.other_cost > 0:
            cost_data.append(['Inne', self._format_currency(costs.other_cost)])
        
        cost_data.append(['', ''])  # Separator
        cost_data.append(['SUMA NETTO', self._format_currency(costs.subtotal)])
        cost_data.append([f'Marża ({self._format_percent(costs.margin_percent)})', 
                         self._format_currency(costs.margin_value)])
        
        cost_table = Table(cost_data, colWidths=[300, 150])
        cost_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -2), 0.5, self.COLOR_GRAY),
            ('LINEABOVE', (0, -2), (-1, -2), 1, self.COLOR_DARK),
            ('FONTNAME', (0, -2), (-1, -1), 'Helvetica-Bold'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        
        self.elements.append(cost_table)
        self.elements.append(Spacer(1, 5*mm))
        
        # Suma końcowa
        total_table = Table(
            [['RAZEM DO ZAPŁATY:', self._format_currency(costs.total)]],
            colWidths=[300, 150]
        )
        total_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.COLOR_SUCCESS),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 14),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        
        self.elements.append(total_table)
        self.elements.append(Spacer(1, 10*mm))
    
    def _add_footer(self):
        """Dodaj stopkę"""
        # Uwagi
        if self.report.notes:
            self.elements.append(Paragraph("📝 UWAGI", self.styles['SectionHeader']))
            self.elements.append(Paragraph(self.report.notes, self.styles['NormalText']))
            self.elements.append(Spacer(1, 5*mm))
        
        # Warunki
        if self.report.terms:
            self.elements.append(Paragraph("📋 WARUNKI", self.styles['SectionHeader']))
            self.elements.append(Paragraph(self.report.terms, self.styles['SmallText']))
        else:
            # Domyślne warunki
            default_terms = """
            • Ceny netto, do kwoty należy doliczyć VAT 23%
            • Termin realizacji: do uzgodnienia
            • Warunki płatności: przelew 14 dni od daty wystawienia faktury
            • Oferta ważna 14 dni od daty wystawienia
            • Ostateczna cena może ulec zmianie po weryfikacji dokumentacji technicznej
            """
            self.elements.append(Paragraph("📋 WARUNKI", self.styles['SectionHeader']))
            self.elements.append(Paragraph(default_terms, self.styles['SmallText']))
        
        # Separator
        self.elements.append(Spacer(1, 10*mm))
        self.elements.append(HRFlowable(
            width="100%", thickness=1, color=self.COLOR_GRAY,
            spaceBefore=5, spaceAfter=5
        ))
        
        # Podpis
        footer_text = f"Wygenerowano: {datetime.now().strftime('%d.%m.%Y %H:%M')} | NewERP Manufacturing System"
        self.elements.append(Paragraph(footer_text, self.styles['SmallText']))


def generate_pdf_report(report: QuotationReport, output_path: str) -> bool:
    """Funkcja pomocnicza do generowania PDF"""
    generator = PDFReportGenerator(report)
    return generator.generate(output_path)
