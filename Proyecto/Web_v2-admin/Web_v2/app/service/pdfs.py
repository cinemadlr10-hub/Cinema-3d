# cinema/services/pdfs.py
# -*- coding: utf-8 -*-
"""
Generación de comprobantes en PDF para tickets/entradas.

Dependencias:
  - fpdf2
  - Flask (solo para current_app)

Uso típico (desde un blueprint):
    from cinema.services.pdfs import generar_comprobante_pdf
    pdf_path = generar_comprobante_pdf(
        trx_id=trx_id,
        cliente=nombre_cliente,
        email=email,
        pelicula=pelicula_titulo,
        fecha_funcion="2025-09-15",
        hora_funcion="20:30",
        sala="Sala 1",
        asientos=["B5", "B6"],
        combos=[{"nombre": "Combo Pop + Gaseosa", "cantidad": 1, "precio": 4500.00}],
        total=12900.00,
        sucursal=session.get("branch") or current_app.config.get("DEFAULT_BRANCH"),
        qr_path=qr_path,  # opcional; si no existe, se omite
    )
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from typing import Iterable, Mapping, Optional, Sequence, Union

from fpdf import FPDF
from fpdf.errors import FPDFException
from flask import current_app


class PDFGenerationError(Exception):
    """Error al generar el PDF del comprobante."""


Number = Union[int, float]
ComboDict = Mapping[str, Union[str, Number]]
StrSeq = Sequence[str]


# ---------------------------------------------------------------------
# Utils de FS / formateo
# ---------------------------------------------------------------------
def _ensure_dir(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def _abs_storage_dir(rel_or_abs: str) -> str:
    # Si es relativo, referencia a la carpeta raíz de la app Flask
    if os.path.isabs(rel_or_abs):
        return rel_or_abs
    base = getattr(current_app, "root_path", os.getcwd())
    return os.path.join(base, rel_or_abs)


def _format_currency(value: Number) -> str:
    try:
        return f"$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return f"$ {value}"


def _normalize_asientos(asientos: Union[str, Iterable[str], None]) -> list[str]:
    if asientos is None:
        return []
    if isinstance(asientos, str):
        # Permitir "A1, A2, A3"
        parts = [x.strip() for x in asientos.split(",") if x.strip()]
        return parts
    return [str(x).strip() for x in asientos if str(x).strip()]


def _normalize_combos(combos: Optional[Iterable[ComboDict]]) -> list[dict]:
    norm: list[dict] = []
    if not combos:
        return norm
    for c in combos:
        nombre = str(c.get("nombre", "")).strip()
        try:
            cantidad = int(c.get("cantidad", 0))
        except Exception:
            cantidad = 0
        try:
            precio = float(c.get("precio", 0.0))
        except Exception:
            precio = 0.0
        if nombre and cantidad > 0:
            norm.append({"nombre": nombre, "cantidad": cantidad, "precio": precio})
    return norm


# ---------------------------------------------------------------------
# Helpers robustos para layout con FPDF (evita "Not enough horizontal space")
# ---------------------------------------------------------------------
def _avail_width(pdf: FPDF) -> float:
    """Ancho útil total (página - márgenes)."""
    return float(pdf.w) - float(pdf.l_margin) - float(pdf.r_margin)


def _remain_width(pdf: FPDF) -> float:
    """Ancho restante desde X actual hasta margen derecho."""
    return float(pdf.w) - float(pdf.r_margin) - float(pdf.get_x())


def _ensure_w(pdf: FPDF, requested: float | None, min_w: float = 20.0) -> float:
    """Asegura un ancho positivo y razonable para poder renderizar texto."""
    if requested is None or requested <= 0:
        w = _remain_width(pdf)
    else:
        w = requested
    return max(min_w, float(w))


def _soft_wrap_tokens(text: str, hard_every: int = 28) -> str:
    """
    Inserta espacios suaves dentro de tokens sin espacios (emails larguísimos, hashes, etc.)
    para permitir corte de línea. No rompe palabras normales.
    """
    def breaker(m):
        s = m.group(0)
        return " ".join(s[i:i + hard_every] for i in range(0, len(s), hard_every))

    # tokens ≥ hard_every sin separadores “amables”
    return re.sub(r"[^\s\-_/.:@]{%d,}" % hard_every, breaker, text or "-")


def _safe_multicell(pdf: FPDF, w: float | None, h: float, txt: str, align: str = "L"):
    """
    multi_cell tolerante: garantiza ancho válido, reintenta con font-size menor si es necesario.
    """
    txt = _soft_wrap_tokens(str(txt))
    width = _ensure_w(pdf, w)
    family = pdf.font_family or "Helvetica"
    style = pdf.font_style or ""
    size = pdf.font_size_pt or 11

    try:
        pdf.multi_cell(width, h, txt, align=align)
        return
    except FPDFException:
        # Reintento: mover a nueva línea, resetear X y usar todo el ancho útil
        pdf.ln(h)
        pdf.set_x(pdf.l_margin)
        width = _ensure_w(pdf, _avail_width(pdf))
        try:
            pdf.multi_cell(width, h, txt, align=align)
            return
        except FPDFException:
            # último intento: bajar fuente 1pt
            try:
                pdf.set_font(family, style, max(8, size - 1))
                pdf.multi_cell(width, h, txt, align=align)
            finally:
                pdf.set_font(family, style, size)


# ---------------------------------------------------------------------
# Bloques de UI PDF
# ---------------------------------------------------------------------
def _kv(pdf: FPDF, k: str, v: str, w_key: float = 40.0, line_h: float = 6.0) -> None:
    """
    Imprime una línea Clave:Valor (clave en bold) de forma segura:
    - Asegura espacio horizontal; si no alcanza, baja de línea y resetea X.
    - El valor usa multi_cell “tolerante” para evitar excepciones.
    """
    # Si el espacio restante no alcanza para la clave + mínimo valor, forzar salto
    min_val_w = 24.0
    need = w_key + min_val_w
    if _remain_width(pdf) < need:
        pdf.ln(line_h)
        pdf.set_x(pdf.l_margin)

    family = pdf.font_family or "Helvetica"
    size = pdf.font_size_pt or 11

    # Clave
    pdf.set_font(family, "B", size)
    pdf.cell(w_key, line_h, k, 0, 0)

    # Valor
    pdf.set_font(family, "", size)
    v_w = _avail_width(pdf) - w_key
    v_w = _ensure_w(pdf, v_w, min_w=min_val_w)
    _safe_multicell(pdf, v_w, line_h, v, align="L")
    # multi_cell deja X en margen izquierdo; no agregamos ln extra.


def _subtitle(pdf: FPDF, text: str) -> None:
    pdf.ln(2)
    family = pdf.font_family or "Helvetica"
    size = pdf.font_size_pt or 11
    pdf.set_font(family, "B", max(10, int(size)))
    pdf.cell(0, 7, text, 0, 1)
    pdf.set_font(family, "", size)


def _draw_header(pdf: FPDF, sucursal: str, verif_code: str) -> None:
    family = pdf.font_family or "Helvetica"
    pdf.set_font(family, "B", 18)
    pdf.cell(0, 10, "Comprobante de Compra", 0, 1, "C")

    pdf.set_font(family, "", 11)
    _safe_multicell(pdf, 0, 6, f"Sucursal: {sucursal}", align="C")
    pdf.set_font(family, "I", 9)
    _safe_multicell(pdf, 0, 5, f"Código verificación: {verif_code}", align="C")
    pdf.ln(2)


# ---------------------------------------------------------------------
# Generación principal
# ---------------------------------------------------------------------
def generar_comprobante_pdf(
    *,
    trx_id: int,
    cliente: str,
    email: str,
    pelicula: str,
    fecha_funcion: str,
    hora_funcion: str,
    sala: str,
    asientos: Union[str, Iterable[str]],
    combos: Optional[Iterable[ComboDict]],
    total: Number,
    sucursal: str,
    qr_path: Optional[str] = None,
    filename: Optional[str] = None,
) -> str:
    """
    Genera un PDF de comprobante y devuelve la ruta absoluta del archivo.

    Raises:
        PDFGenerationError: si ocurre un error al crear o guardar el PDF.
    """
    try:
        # Directorio de salida desde config (con fallback)
        out_dir_cfg = current_app.config.get("COMPROBANTES_DIR", "static/comprobantes")
        out_dir = _abs_storage_dir(out_dir_cfg)
        _ensure_dir(out_dir)

        # Datos normalizados
        asientos_list = _normalize_asientos(asientos)
        combos_list = _normalize_combos(combos)
        fecha_emision = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        verif_code = uuid.uuid4().hex[:12].upper()

        # Nombre de archivo
        if not filename:
            filename = f"comprobante_trx_{trx_id}.pdf"
        pdf_path = os.path.join(out_dir, filename)

        # === Comienzo del PDF ===
        pdf = FPDF(orientation="P", unit="mm", format="A4")
        # Márgenes consistentes (importante para que _remain_width calcule bien)
        pdf.set_left_margin(15)
        pdf.set_right_margin(15)
        pdf.set_top_margin(15)
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Helvetica", "", 11)

        # Encabezado
        _draw_header(pdf, sucursal=sucursal or "-", verif_code=verif_code)

        # Bloque de datos de operación
        _subtitle(pdf, "Datos de la operación")
        _kv(pdf, "Transacción:", f"#{trx_id}")
        _kv(pdf, "Cliente:", cliente or "-")
        _kv(pdf, "Email:", email or "-")
        _kv(pdf, "Fecha emisión:", fecha_emision)

        # Bloque de función
        _subtitle(pdf, "Detalles de la función")
        _kv(pdf, "Película:", pelicula or "-")
        _kv(pdf, "Fecha:", fecha_funcion or "-")
        _kv(pdf, "Hora:", hora_funcion or "-")
        _kv(pdf, "Sala:", sala or "-")
        _kv(pdf, "Asientos:", ", ".join(asientos_list) if asientos_list else "-")

        # Bloque de combos (si hay)
        if combos_list:
            _subtitle(pdf, "Combos")
            family = pdf.font_family or "Helvetica"
            size = pdf.font_size_pt or 11

            pdf.set_font(family, "B", size)
            # Cabecera
            pdf.cell(120, 7, "Descripción", 0, 0)
            pdf.cell(25, 7, "Cant.", 0, 0, "R")
            pdf.cell(0, 7, "Subtotal", 0, 1, "R")
            pdf.set_font(family, "", size)

            for c in combos_list:
                nombre = c["nombre"]
                cantidad = int(c["cantidad"])
                precio = float(c["precio"])
                subtotal = cantidad * precio

                # Descripción (multi_line segura)
                y_before = pdf.get_y()
                _safe_multicell(pdf, 120, 6, f"{nombre}", align="L")
                y_after = pdf.get_y()
                height_used = max(6, y_after - y_before)

                # Cantidad y Subtotal alineados a la derecha, respetando margen izquierdo real
                pdf.set_xy(pdf.l_margin + 120, y_before)
                pdf.cell(25, height_used, str(cantidad), 0, 0, "R")
                pdf.cell(0, height_used, _format_currency(subtotal), 0, 1, "R")

        # Total
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, f"TOTAL: {_format_currency(total)}", 0, 1, "R")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(90)
        _safe_multicell(
            pdf,
            0,
            5,
            "Este comprobante es válido como constancia de compra. "
            "Conservar para eventuales controles en la entrada.",
        )
        pdf.set_text_color(0)

        # QR opcional
        if qr_path:
            try:
                abs_qr = qr_path
                if not os.path.isabs(abs_qr):
                    # Si viene relativo, resolver respecto a raíz de la app
                    abs_qr = os.path.join(getattr(current_app, "root_path", os.getcwd()), qr_path)
                if os.path.exists(abs_qr):
                    pdf.ln(4)
                    _subtitle(pdf, "Verificación rápida (QR)")
                    # Inserta la imagen (tamaño aprox. 45x45mm)
                    x = pdf.get_x()
                    y = pdf.get_y()
                    pdf.image(abs_qr, x=x, y=y, w=45, h=45)
                    pdf.set_xy(x + 52, y + 6)
                    pdf.set_font("Helvetica", "", 10)
                    _safe_multicell(
                        pdf,
                        0,
                        5,
                        "Escanee el código para validar los datos del ticket "
                        "o acceder al digital en su cuenta (si corresponde).",
                    )
                    pdf.ln(43)
            except Exception:
                # No abortar por problemas de imagen; el ticket sigue siendo válido
                pass

        # Footer simple
        pdf.set_y(-20)
        pdf.set_font("Helvetica", "I", 9)
        _safe_multicell(pdf, 0, 6, "Gracias por su compra. ¡Que disfrute la función!", align="C")
        _safe_multicell(pdf, 0, 5, "Cinema3D · Sistema de Venta de Entradas", align="C")

        # Guardar
        pdf.output(pdf_path)

        return pdf_path

    except Exception as exc:
        raise PDFGenerationError(f"No se pudo generar el PDF (trx_id={trx_id}): {exc}") from exc
