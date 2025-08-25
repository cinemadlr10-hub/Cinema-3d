# -*- coding: utf-8 -*-
"""
App Flask básica para registro de usuarios (cine)
- Base de datos: SQLite (archivo usuarios.db en la carpeta del proyecto)
- Validaciones servidor: campos obligatorios, DNI de 8 dígitos, longitudes, email válido
- Usa plantilla templates/registro.html para el formulario
"""

import re
import sqlite3
from pathlib import Path

from flask import Flask, render_template, request
from werkzeug.security import generate_password_hash

# ---------------------------
# Configuracion
# ---------------------------
DB_NAME = "usuarios.db"

# Crear la aplicacion Flask
app = Flask(__name__)


# ---------------------------
# Base de datos
# ---------------------------
def get_conn():
    """Devuelve una conexion a la base (con row_factory si queres usar nombres de columna)."""
    conn = sqlite3.connect(DB_NAME)
    return conn

def init_db():
    """Crea la base y la tabla 'usuarios' si no existen."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            apellido TEXT NOT NULL,
            tipo_documento TEXT NOT NULL CHECK (tipo_documento IN ('DNI','CI','LE','LC')),
            nro_documento TEXT NOT NULL,
            contrasena TEXT NOT NULL,   -- guardamos el hash
            direccion TEXT,
            ciudad TEXT,
            provincia TEXT,
            codigo_postal TEXT,
            telefono TEXT,
            email TEXT
        );
    """)
    conn.commit()
    conn.close()


# ---------------------------
# Rutas
# ---------------------------
@app.route("/")
def inicio():
    """Pantalla simple para verificar que todo corre y la base existe."""
    db_ok = Path(DB_NAME).exists()
    return f"Inicio Cine - Base de datos: {'OK' if db_ok else 'NO CREADA'} - Ir a /registro"


@app.route("/registro", methods=["GET", "POST"])
def registro():
    """
    Muestra el formulario (GET) y guarda (POST) con validaciones del lado servidor.
    - Obligatorios: nombre, apellido, tipo_documento (DNI/CI/LE/LC), nro_documento (8 digitos), contrasena
    - Email opcional, pero si viene debe ser valido
    """
    if request.method == "POST":
        # 1) Tomar datos del form
        nombre = (request.form.get("nombre") or "").strip()
        apellido = (request.form.get("apellido") or "").strip()
        tipo_documento = (request.form.get("tipo_documento") or "").strip()
        nro_documento = (request.form.get("nro_documento") or "").strip()
        contrasena_plana = request.form.get("contrasena") or ""
        direccion = (request.form.get("direccion") or "").strip()
        ciudad = (request.form.get("ciudad") or "").strip()
        provincia = (request.form.get("provincia") or "").strip()
        codigo_postal = (request.form.get("codigo_postal") or "").strip()
        telefono = (request.form.get("telefono") or "").strip()
        email = (request.form.get("email") or "").strip()

        # 2) Validaciones servidor
        errores = []

        if not (2 <= len(nombre) <= 40):
            errores.append("Nombre invalido (2 a 40 caracteres).")

        if not (2 <= len(apellido) <= 40):
            errores.append("Apellido invalido (2 a 40 caracteres).")

        if tipo_documento not in ("DNI", "CI", "LE", "LC"):
            errores.append("Tipo de documento invalido (usa DNI, CI, LE o LC).")

        # DNI: exactamente 8 digitos
        if not re.fullmatch(r"\d{8}", nro_documento):
            errores.append("El nro de documento debe tener exactamente 8 digitos numericos.")

        if not (6 <= len(contrasena_plana) <= 64):
            errores.append("Contrasena invalida (6 a 64 caracteres).")

        # Email (opcional). Si viene, debe tener formato basico valido.
        if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            errores.append("Email invalido.")

        # 3) Si hay errores, volvemos al form
        if errores:
            return render_template("registro.html", errores=errores, exito=None)

        # 4) Hash de la contrasena y guardado
        contrasena_hash = generate_password_hash(contrasena_plana)

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO usuarios (
                nombre, apellido, tipo_documento, nro_documento, contrasena,
                direccion, ciudad, provincia, codigo_postal, telefono, email
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            nombre, apellido, tipo_documento, nro_documento, contrasena_hash,
            direccion, ciudad, provincia, codigo_postal, telefono, email
        ))
        conn.commit()
        conn.close()

        # 5) Mostrar mensaje de exito
        return render_template("registro.html", errores=None, exito="Usuario registrado correctamente.")

    # GET: mostrar el form
    return render_template("registro.html", errores=None, exito=None)


# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    init_db()           # asegurar tabla
    app.run(debug=True) # levantar servidor
