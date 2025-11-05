# app/blueprints/pago.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple, Dict, Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from flask import (
    Blueprint, current_app, flash, redirect, render_template,
    request, session, url_for
)
import mercadopago

from app.service.qrs import generar_qr
from app.service.pdfs import generar_comprobante_pdf
from app.service.emailer import enviar_ticket
from app.db import get_conn
from app import db as db_mod
from app.data.seed import COMBOS_CATALOG

bp = Blueprint("pago", __name__)

# ---------------------- Helpers MP ---------------------- #
def _get_mp_token() -> str:
    return (os.getenv("MP_ACCESS_TOKEN") or os.getenv("MERCADOPAGO_ACCESS_TOKEN") or "").strip()

def _sdk_mp():
    token = _get_mp_token()
    if not token:
        current_app.logger.error("Mercado Pago: falta MP_ACCESS_TOKEN/MERCADOPAGO_ACCESS_TOKEN")
        raise RuntimeError("Falta MP_ACCESS_TOKEN en el entorno")
    return mercadopago.SDK(token)

def _mp_token_ok() -> Tuple[bool, str]:
    token = _get_mp_token()
    if not token:
        return False, "Falta MP_ACCESS_TOKEN"
    req = Request(
        "https://api.mercadopago.com/users/me",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )
    try:
        with urlopen(req, timeout=10) as r:
            if r.status == 200:
                return True, ""
            return False, f"users/me devolvió status {r.status}"
    except HTTPError as e:
        try:
            body = e.read().decode("utf-8")
        except Exception:
            body = ""
        return False, f"{e.code} {e.reason} {body}".strip()
    except URLError as e:
        return False, f"Error de red hacia MP: {e.reason}"
    except Exception as e:
        return False, f"Excepción verificando token: {e}"

# ---------------------- Helpers APP ---------------------- #
def _combos_from_session() -> List[dict]:
    ids = [int(x) for x in session.get("combos", [])]
    idset = set(ids)
    return [c for c in COMBOS_CATALOG if c["id"] in idset]

def _seleccion_from_session() -> dict:
    return session.get("movie_selection", {}) or {}

def _seats_from_session() -> List[str]:
    return session.get("seats", []) or []

def _precio_entrada() -> Decimal:
    raw = str(current_app.config.get("TICKET_PRICE", "5000"))
    try:
        return Decimal(raw)
    except Exception:
        return Decimal("5000")

def _calcular_totales() -> Tuple[Decimal, Decimal, Decimal, list, list, dict]:
    TWO = Decimal("0.01")
    precio = Decimal(str(_precio_entrada()))
    seats = _seats_from_session()
    combos = _combos_from_session()
    seleccion = _seleccion_from_session()

    total_entradas = (precio * Decimal(len(seats))).quantize(TWO, rounding=ROUND_HALF_UP)
    total_combos = sum(
        (Decimal(str(c.get("precio", 0))) for c in combos),
        Decimal("0")
    ).quantize(TWO, rounding=ROUND_HALF_UP)

    total = (total_entradas + total_combos).quantize(TWO, rounding=ROUND_HALF_UP)
    return total_entradas, total_combos, total, combos, seats, seleccion

def _to_cents(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))

def _is_local(url: str) -> bool:
    return ("127.0.0.1" in url) or ("localhost" in url) or url.startswith("http://")

def _abs_url_for(endpoint: str) -> str:
    """
    Construye URL absoluta priorizando ngrok si detecta túnel.
    Si no, usa PUBLIC_BASE_URL/BASE_URL o request.host_url.
    """
    rel = url_for(endpoint, _external=False)
    host = (request.host_url or "").strip()  # p.ej. https://xxxx.ngrok-free.dev/
    env_base = (os.getenv("PUBLIC_BASE_URL") or os.getenv("BASE_URL") or "").strip()
    base = host if "ngrok" in host.lower() else (env_base or host)
    if base and not base.endswith("/"):
        base += "/"
    return urljoin(base, rel.lstrip("/"))

def _valid_url(u: str) -> bool:
    return bool(u) and u.startswith(("http://", "https://"))

def _marcar(trx_id: int, estado: str) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE transacciones SET estado=?, fecha_actualizacion=? WHERE id=?",
        (estado, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), trx_id),
    )
    conn.commit()

# ---------------------- Pago MP ---------------------- #
def _iniciar_pago_mp(email: str):
    # Requiere selección previa
    t_ent, t_combo, total, combos, seats, sel = _calcular_totales()
    if not seats or not sel:
        flash("Selección de función y asientos requerida.", "warning")
        return redirect(url_for("pago.pago"))

    # Email: SIEMPRE desde sesión de usuario logueado
    email = (email or "").strip()
    if not email:
        # nunca bucle: mandá a login con next=/pago
        return redirect(url_for("auth.login", next=url_for("pago.pago")))

    session["checkout_email"] = email
    session.modified = True

    ok_token, detalle = _mp_token_ok()
    if not ok_token:
        current_app.logger.error("MP token inválido: %s", detalle)
        flash(f"No se pudo iniciar el pago con Mercado Pago: credencial inválida ({detalle})", "danger")
        return redirect(url_for("pago.pago"))

    # Crear trx local
    conn = get_conn()
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO transacciones (usuario_email, monto_cents, estado, created_at, auth_code)
        VALUES (?,?,?,?,?)
        """,
        (email, _to_cents(total), "INICIADO", now_iso, f"MP-{datetime.now().strftime('%H%M%S')}"),
    )
    trx_id = int(cur.lastrowid or 0)
    conn.commit()
    session["trx_id_mp"] = trx_id
    session.modified = True

    # SDK
    try:
        sdk = _sdk_mp()
    except Exception:
        flash("No se pudo iniciar el pago: error de credenciales de Mercado Pago (ver logs).", "danger")
        return redirect(url_for("pago.pago"))

    # URLs
    success = _abs_url_for("pago.mp_success")
    failure = _abs_url_for("pago.mp_failure")
    pending = _abs_url_for("pago.mp_pending")
    webhook = _abs_url_for("pago.mp_webhook")
    if not (_valid_url(success) and _valid_url(failure) and _valid_url(pending)):
        current_app.logger.error("Back URLs inválidas: %s | %s | %s", success, failure, pending)
        flash("No se pudo iniciar el pago: back_urls inválidas (ver logs).", "danger")
        return redirect(url_for("pago.pago"))

    currency = os.getenv("CURRENCY_ID", "ARS")
    pref_data: Dict[str, Any] = {
        "items": [{
            "title": sel.get("titulo", "Entrada de cine"),
            "quantity": 1,
            "currency_id": currency,
            "unit_price": float(total),
        }],
        "payer": {"email": email},
        "back_urls": {"success": success, "failure": failure, "pending": pending},
        "statement_descriptor": "CINEMA3D",
        "metadata": {
            "trx_id": trx_id,
            "movie_id": sel.get("id"),
            "titulo": sel.get("titulo"),
            "fecha": sel.get("fecha"),
            "hora": sel.get("hora"),
            "sala": sel.get("sala"),
            "seats": ",".join(seats),
        },
        "external_reference": str(trx_id),
        "binary_mode": os.getenv("MP_BINARY_MODE", "1") in ("1", "true", "True"),
    }
    # ⚠️ Esta es la condición clave para el retorno automático
    if success.startswith("https://"): 
        pref_data["auto_return"] = "approved"
    if not _is_local(webhook):
        pref_data["notification_url"] = webhook

    # Crear preferencia
    try:
        pref = sdk.preference().create(pref_data)
    except Exception as e:
        current_app.logger.exception("Excepción creando preferencia MP: %s", e)
        flash("No se pudo iniciar el pago con Mercado Pago (excepción en SDK).", "danger")
        return redirect(url_for("pago.pago"))

    status = pref.get("status")
    resp = pref.get("response", {}) or {}
    init_point = resp.get("init_point")
    pref_id = resp.get("id")
    if status not in (200, 201) or not init_point:
        current_app.logger.error("Error creando preferencia MP | status=%s | resp=%s", status, resp)
        msg = resp.get("message")
        flash(f"No se pudo iniciar el pago con Mercado Pago: {msg or 'ver logs'}", "danger")
        return redirect(url_for("pago.pago"))

    conn.execute(
        "UPDATE transacciones SET estado=?, mp_preference_id=? WHERE id=?",
        ("PENDIENTE", str(pref_id), trx_id),
    )
    conn.commit()

    return redirect(init_point)

# ---------------------- Rutas ---------------------- #
@bp.route("/pago", methods=["GET", "POST"])
def pago():
    """
    Login obligatorio:
    - Si no hay user_email -> /login?next=/pago
    - GET: muestra resumen
    - POST: inicia MP con email de sesión
    """
    user = session.get("user_autofill") or {}
    user_email = (user.get("email") or "").strip()
    if not user_email:
        return redirect(url_for("auth.login", next=url_for("pago.pago")))

    if request.method == "POST":
        return _iniciar_pago_mp(user_email)

    t_ent, t_combo, total, combos, seats, sel = _calcular_totales()
    if not seats or not sel:
        flash("Primero elegí función y asientos.", "warning")

    return render_template(
        "pago.html",
        errores=None, exito=None, email=user_email,
        nombre_tarjeta="",
        seleccion=sel, seats=seats, combos=combos,
        monto_sugerido=f"{total:.2f}",
        total_entradas=t_ent, total_combos=t_combo, total=total
    )

# ---------------------- Callbacks MP ---------------------- #
@bp.route("/pago/mp/success")
def mp_success():
    # No dependemos de sesión para reconstruir la compra
    pid = request.args.get("payment_id") or request.args.get("collection_id")
    if not pid:
        flash("Faltan datos de pago devueltos por Mercado Pago.", "danger")
        return redirect(url_for("pago.pago"))

    sdk = _sdk_mp()
    pay = sdk.payment().get(pid)
    resp = pay.get("response", {}) or {}

    status = (resp.get("status") or "").lower()
    trx_id_from_session = session.get("trx_id_mp")
    if status != "approved":
        if trx_id_from_session:
            _marcar(trx_id_from_session, "RECHAZADA")
        flash("El pago no fue aprobado.", "warning")
        return redirect(url_for("pago.mp_failure"))

    # Fuente de verdad: external_reference
    trx_id_raw = (resp.get("external_reference") or "").strip()
    try:
        trx_id = int(trx_id_raw)
    except Exception:
        trx_id = trx_id_from_session
    if not trx_id:
        flash("No se pudo asociar el pago a una transacción local.", "warning")
        return redirect(url_for("pago.pago"))

    # Metadata enviada al crear preferencia
    md = resp.get("metadata") or {}
    sel = {
        "id": md.get("movie_id"),
        "titulo": md.get("titulo") or md.get("movie_title") or "Entrada de cine",
        "fecha": md.get("fecha"),
        "hora": md.get("hora"),
        "sala": md.get("sala"),
    }
    seats_md = (md.get("seats") or "")
    seats = [s for s in seats_md.split(",") if s] if seats_md else (session.get("seats") or [])

    # Total desde el pago (fallback a cálculo)
    try:
        total = Decimal(str(resp.get("transaction_amount")))
    except Exception:
        _, _, total, _, _, _ = _calcular_totales()

    # Confirmación de butacas (best effort)
    try:
        hold_token = session.get("hold_token")
        confirmados = db_mod.confirm_seats(
            token=hold_token,
            movie_id=sel.get("id"), fecha=sel.get("fecha"),
            hora=sel.get("hora"), sala=sel.get("sala"),
            usuario_email=session.get("user_autofill", {}).get("email"),
            trx_id=trx_id,
        )
        if not confirmados:
            confirmados = seats
    except Exception:
        confirmados = seats

    # Datos de medio de pago
    brand = (resp.get("payment_method", {}) or {}).get("id")
    last4 = (resp.get("card", {}) or {}).get("last_four_digits")

    conn = get_conn()
    conn.execute(
        "UPDATE transacciones SET estado=?, brand=?, last4=?, mp_payment_id=?, fecha_actualizacion=? WHERE id=?",
        ("APROBADO", brand, last4, str(pid), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), trx_id),
    )
    conn.commit()

    # E-mail del comprador: primero el usuario logueado; si no, payer MP
    email = (session.get("user_autofill", {}) or {}).get("email", "")
    if not email:
        payer = resp.get("payer") or {}
        email = (payer.get("email") or "").strip()

    sucursal = session.get("branch") or current_app.config.get("DEFAULT_BRANCH", "-")
    auth_code = f"MP-{pid}"
    qr_path = generar_qr(trx_id=trx_id, verify_url=None, extra={"email": email, "auth": auth_code})
    pdf_path = generar_comprobante_pdf(
        trx_id=trx_id, cliente=email or "-", email=email or "-",
        pelicula=sel.get("titulo", "-"),
        fecha_funcion=sel.get("fecha", "-"), hora_funcion=sel.get("hora", "-"),
        sala=sel.get("sala", "-"),
        asientos=confirmados or seats,
        combos=[],  # si querés combos, incluilos en metadata
        total=float(total or 0),
        sucursal=sucursal, qr_path=qr_path,
    )

    # Mail cliente
    try:
        enviar_ticket(
            destino=email,
            asunto=f"Comprobante TRX #{trx_id}",
            cuerpo=(f"Gracias por su compra.\n\nSucursal: {sucursal}\n"
                    f"Película: {sel.get('titulo','-')}\n"
                    f"Fecha/Hora: {sel.get('fecha','-')} {sel.get('hora','-')}\n"
                    f"Asientos: {', '.join(confirmados or seats) if (confirmados or seats) else '-'}\n"
                    f"Monto: ${total:.2f}\nCódigo de autorización: {auth_code}\n"),
            adjunto_path=pdf_path,
        )
    except Exception as e:
        current_app.logger.warning("Email al cliente no enviado: %s", e)

    # Mail interno (opcional)
    sales_email = (os.getenv("CINEMA_SALES_EMAIL") or "").strip()
    if sales_email:
        try:
            enviar_ticket(
                destino=sales_email,
                asunto=f"[Copia interna] TRX #{trx_id} aprobada",
                cuerpo=(f"Se registró una venta aprobada.\n\nCliente: {email or '-'}\n"
                        f"Sucursal: {sucursal}\n"
                        f"Película: {sel.get('titulo','-')}\n"
                        f"Fecha/Hora: {sel.get('fecha','-')} {sel.get('hora','-')}\n"
                        f"Asientos: {', '.join(confirmados or seats) if (confirmados or seats) else '-'}\n"
                        f"Total: ${total:.2f}\nBrand/Last4: {brand or '-'} • {last4 or '----'}\n"
                        f"Auth: {auth_code}\nTRX local: {trx_id}\n"),
            )
        except Exception as e:
            current_app.logger.warning("Email interno (cine) no enviado: %s", e)

    comprobante_url = url_for("archivos.descargar_comprobante", trx_id=trx_id)

    # Limpieza best effort
    for k in ("seats", "hold_token", "combos", "trx_id_mp", "checkout_email"):
        session.pop(k, None)
    session.modified = True

    # ⬅️ ESTE ES EL PASO QUE VUELVE A pago_ok.html
    return render_template(
        "pago_ok.html",
        exito="¡Pago aprobado!",
        trx_id=trx_id,
        comprobante_url=comprobante_url,
        seleccion=sel,
        seats=(confirmados or seats),
        combos=[],
        total=float(total or 0),
        brand=brand,
        last4=last4,
        auth_code=auth_code,
    )

@bp.route("/pago/mp/failure")
def mp_failure():
    flash("El pago fue cancelado o rechazado.", "warning")
    return redirect(url_for("pago.pago"))

@bp.route("/pago/mp/pending")
def mp_pending():
    flash("El pago quedó pendiente de acreditación.", "info")
    return redirect(url_for("pago.pago"))

@bp.route("/pago/mp/webhook", methods=["POST"])
def mp_webhook():
    """
    Marca APROBADO cuando MP notifica un payment approved.
    No envía mails ni genera PDF (eso lo hace /success).
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        current_app.logger.info("MP webhook: %s", data)

        topic = data.get("type") or data.get("topic")
        pid = (data.get("data", {}) or {}).get("id") or data.get("id")

        if topic == "payment" and pid:
            sdk = _sdk_mp()
            pay = sdk.payment().get(pid)
            resp = pay.get("response", {}) or {}
            if (resp.get("status") or "").lower() == "approved":
                try:
                    trx_id = int(resp.get("external_reference") or 0)
                except Exception:
                    trx_id = 0
                if trx_id:
                    _marcar(trx_id, "APROBADO")
                    current_app.logger.info("Webhook MP: pago %s aprobado (trx %s)", pid, trx_id)
    except Exception as e:
        current_app.logger.warning("Webhook MP error: %s", e)

    return ("", 200)