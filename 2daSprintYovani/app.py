# -*- coding: utf-8 -*-
"""
Flask - Pagos (con Flask-Mail + Mailtrap/Gmail)
- /               : inicio
- /pago           : formulario -> valida -> guarda -> genera QR -> envía email al comprador
- /transacciones  : lista de pagos
BD: usuarios.db (tabla transacciones).  NUNCA guardamos PAN/CVV.
"""

import os
import re
import sqlite3
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, request
from flask_mail import Mail, Message           # envío de mails
import qrcode                                  # QR
from dotenv import load_dotenv                 # .env

# ---------------------------
# App y configuración
# ---------------------------
app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
DB_NAME = "usuarios.db"

# Cargar variables .env (si existen)
load_dotenv()

# Podés configurar por .env (recomendado)
#   SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASS, SENDER_NAME, EMAIL_DEBUG
SMTP_SERVER = os.getenv("SMTP_SERVER", "sandbox.smtp.mailtrap.io")
SMTP_PORT   = int(os.getenv("SMTP_PORT", "2525"))
SMTP_USER   = os.getenv("SMTP_USER", "")
SMTP_PASS   = os.getenv("SMTP_PASS", "")
SENDER_NAME = os.getenv("SENDER_NAME", "Cine")
EMAIL_DEBUG = os.getenv("EMAIL_DEBUG", "0") == "1"

# Config Flask-Mail (puede ser Mailtrap, Gmail u otro SMTP)
app.config["MAIL_SERVER"]   = SMTP_SERVER
app.config["MAIL_PORT"]     = SMTP_PORT
app.config["MAIL_USERNAME"] = SMTP_USER
app.config["MAIL_PASSWORD"] = SMTP_PASS
# Para Mailtrap: TLS True / SSL False. Para Gmail suele ser 587 (TLS).
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USE_SSL"] = False
mail = Mail(app)

# Carpeta para QR
QR_DIR = BASE_DIR / "static" / "qr"
QR_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------
# Helpers de validación
# ---------------------------
def luhn_ok(pan: str) -> bool:
    """Valida PAN con Luhn."""
    pan = re.sub(r"\D", "", pan)
    if not pan:
        return False
    total = 0
    inv = pan[::-1]
    for i, ch in enumerate(inv):
        d = ord(ch) - 48
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0

def detectar_brand(pan: str) -> str:
    """Detecta marca simple por BIN/prefijo."""
    pan = re.sub(r"\D", "", pan)
    if re.match(r"^4\d{12,18}$", pan):
        return "VISA"
    if re.match(r"^(5[1-5]\d{14}|2(2[2-9]\d{12}|[3-6]\d{13}|7[01]\d{12}|720\d{12}))$", pan):
        return "MASTERCARD"
    if re.match(r"^3[47]\d{13}$", pan):
        return "AMEX"
    return "OTRA"

def cvv_valido(brand: str, cvv: str) -> bool:
    """3 dígitos Visa/Master, 4 Amex."""
    return bool(re.fullmatch(r"\d{4}", cvv)) if brand == "AMEX" else bool(re.fullmatch(r"\d{3}", cvv))

def vencimiento_valido(mes: int, anio: int) -> bool:
    """Mes/Año no en el pasado (mes actual válido)."""
    try:
        if not (1 <= mes <= 12):
            return False
        now = datetime.now()
        if anio < now.year or (anio == now.year and mes < now.month):
            return False
        return True
    except:
        return False

# ---------------------------
# DB helpers
# ---------------------------
def init_db():
    """Crea tabla transacciones si no existe."""
    conn = sqlite3.connect(str(BASE_DIR / DB_NAME))
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_email TEXT,
            monto_cents INTEGER NOT NULL,
            brand TEXT NOT NULL,
            last4 TEXT NOT NULL,
            exp_mes INTEGER NOT NULL,
            exp_anio INTEGER NOT NULL,
            estado TEXT NOT NULL,
            auth_code TEXT NOT NULL,
            created_at TEXT NOT NULL,
            qr_filename TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()

# ---------------------------
# Email helper (Flask-Mail)
# ---------------------------
def enviar_email_con_qr(destino: str, asunto: str, cuerpo: str, qr_path: Path):
    """
    Envía email al comprador con el QR adjunto (PNG).
    Usa la config de Flask-Mail. Si falta config, solo imprime y no rompe.
    """
    if not (app.config["MAIL_SERVER"] and app.config["MAIL_USERNAME"] and app.config["MAIL_PASSWORD"]):
        print("[EMAIL] SMTP no configurado. Simulando envío a:", destino)
        return

    sender = f"{SENDER_NAME} <{app.config['MAIL_USERNAME']}>"
    msg = Message(asunto, sender=sender, recipients=[destino])
    msg.body = cuerpo

    if qr_path and qr_path.exists():
        with open(qr_path, "rb") as f:
            msg.attach(qr_path.name, "image/png", f.read())

    if EMAIL_DEBUG:
        print(f"[EMAIL] Enviando a: {destino} via {app.config['MAIL_SERVER']}:{app.config['MAIL_PORT']} como {app.config['MAIL_USERNAME']}")

    mail.send(msg)

# ---------------------------
# Rutas
# ---------------------------
@app.route("/")
def inicio():
    return render_template("inicio.html")  # links a /pago y /transacciones

@app.route("/pago", methods=["GET", "POST"])
def pago():
    """
    Flujo:
      - Email OBLIGATORIO (destinatario del comprobante)
      - Valida datos tarjeta (Luhn, marca, CVV, vencimiento)
      - Guarda transacción (sin PAN/CVV)
      - Genera QR con código de compra
      - Envía email al comprador con QR adjunto
      - Muestra comprobante y QR en pantalla
    """
    if request.method == "POST":
        errores = []

        # Datos del form
        email = (request.form.get("email") or "").strip()
        monto_str = (request.form.get("monto") or "").strip()
        pan = (request.form.get("pan") or "").replace(" ", "")
        nombre_tarjeta = (request.form.get("nombre_tarjeta") or "").strip()
        try:
            exp_mes = int(request.form.get("exp_mes") or "0")
            exp_anio = int(request.form.get("exp_anio") or "0")
        except:
            exp_mes, exp_anio = 0, 0
        cvv = (request.form.get("cvv") or "").strip()

        # Email obligatorio
        if not email:
            errores.append("El email es obligatorio para enviar el comprobante.")
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            errores.append("Email inválido.")

        # Monto
        try:
            monto = float(monto_str.replace(",", "."))
            if monto <= 0:
                errores.append("El monto debe ser mayor a 0.")
        except:
            errores.append("Monto inválido.")
            monto = 0.0
        monto_cents = int(round(monto * 100))

        # Nombre en tarjeta
        if not nombre_tarjeta or len(nombre_tarjeta) < 2:
            errores.append("Nombre en la tarjeta inválido.")

        # PAN / marca / CVV / vencimiento
        if not luhn_ok(pan):
            errores.append("Número de tarjeta inválido (Luhn).")
        brand = detectar_brand(pan)
        if not cvv_valido(brand, cvv):
            errores.append("CVV inválido para la marca.")
        if not vencimiento_valido(exp_mes, exp_anio):
            errores.append("Tarjeta vencida o fecha inválida.")

        if errores:
            return render_template("pago.html", errores=errores, exito=None)

        # Autorización simulada
        auth_code = f"AUTH{datetime.now().strftime('%H%M%S')}"
        estado = "APROBADO"
        last4 = re.sub(r"\D", "", pan)[-4:]
        now_iso = datetime.now().isoformat(timespec="seconds")

        # Guardar en BD (sin PAN ni CVV)
        conn = sqlite3.connect(str(BASE_DIR / DB_NAME))
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO transacciones (
                usuario_email, monto_cents, brand, last4, exp_mes, exp_anio,
                estado, auth_code, created_at, qr_filename
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (email, monto_cents, brand, last4, exp_mes, exp_anio,
              estado, auth_code, now_iso, ""))
        trx_id = cur.lastrowid

        # Código de compra legible
        codigo_compra = f"TRX-{trx_id}-{auth_code[-6:]}"  # ej: TRX-12-1A2B3C

        # Generar QR con el código incluido
        payload_qr = (
            f"COD:{codigo_compra}|MONTO:{monto_cents}|BRAND:{brand}|"
            f"LAST4:{last4}|FECHA:{now_iso}"
        )
        img = qrcode.make(payload_qr)
        qr_filename = f"trx_{trx_id}.png"
        qr_path = QR_DIR / qr_filename
        img.save(qr_path)

        # Actualizar filename en BD
        cur.execute("UPDATE transacciones SET qr_filename = ? WHERE id = ?", (qr_filename, trx_id))
        conn.commit()
        conn.close()

        # Enviar email al comprador con QR adjunto
        try:
            cuerpo = (
                "Gracias por tu compra en Cine 🎬\n\n"
                f"Código de compra: {codigo_compra}\n"
                f"Transacción: {trx_id}\n"
                f"Monto: ${monto:.2f}\n"
                f"Tarjeta: {brand} **** {last4}\n"
                f"Fecha: {now_iso}\n"
                f"Autorización: {auth_code}\n\n"
                "Adjuntamos el QR de tu comprobante. Mostralo en la entrada.\n"
            )
            enviar_email_con_qr(email, "Confirmación de compra - Cine", cuerpo, qr_path)
        except Exception as ex:
            # No detenemos el flujo si falla el envío
            print("Error enviando email:", ex)

        # Mostrar comprobante en pantalla
        return render_template(
            "pago_ok.html",
            trx_id=trx_id,
            monto=f"{monto:.2f}",
            brand=brand,
            last4=last4,
            fecha=now_iso,
            auth_code=auth_code,
            codigo_compra=codigo_compra,
            qr_file=f"/static/qr/{qr_filename}"
        )

    # GET
    return render_template("pago.html", errores=None, exito=None)

@app.route("/transacciones")
def transacciones():
    """Lista de pagos guardados."""
    conn = sqlite3.connect(str(BASE_DIR / DB_NAME))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT id, usuario_email, monto_cents, brand, last4, exp_mes, exp_anio,
               estado, auth_code, created_at, qr_filename
        FROM transacciones
        ORDER BY id DESC
    """)
    filas = cur.fetchall()
    conn.close()

    trans = []
    for r in filas:
        trans.append({
            "id": r["id"],
            "email": r["usuario_email"] or "",
            "monto": f"${r['monto_cents']/100:.2f}",
            "brand": r["brand"],
            "last4": r["last4"],
            "exp": f"{int(r['exp_mes']):02d}/{r['exp_anio']}",
            "estado": r["estado"],
            "auth": r["auth_code"],
            "fecha": r["created_at"],
            "qr_url": f"/static/qr/{r['qr_filename']}" if r["qr_filename"] else ""
        })

    return render_template("transacciones.html", transacciones=trans)

# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    init_db()
    if EMAIL_DEBUG:
        print("[ENV] MAIL_SERVER:", app.config["MAIL_SERVER"])
        print("[ENV] MAIL_PORT:", app.config["MAIL_PORT"])
        print("[ENV] MAIL_USERNAME:", app.config["MAIL_USERNAME"])
    app.run(debug=True)
