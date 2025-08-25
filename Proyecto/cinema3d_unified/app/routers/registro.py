
import re
import sqlite3
from pathlib import Path
from hashlib import pbkdf2_hmac
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()

DB_NAME = "usuarios.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            apellido TEXT NOT NULL,
            dni TEXT NOT NULL,
            email TEXT,
            password TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()

init_db()

def hash_password(password: str) -> str:
    salt = b"cinema3d_salt"
    h = pbkdf2_hmac("sha256", password.encode(), salt, 100000)
    return h.hex()

def validar(nombre, apellido, dni, email, password):
    errores = []
    if not (2 <= len(nombre) <= 40):
        errores.append("Nombre debe tener entre 2 y 40 caracteres.")
    if not (2 <= len(apellido) <= 40):
        errores.append("Apellido debe tener entre 2 y 40 caracteres.")
    if not re.fullmatch(r"\d{7,8}", dni):
        errores.append("DNI debe tener 7 u 8 dígitos.")
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        errores.append("Email inválido.")
    if len(password) < 6:
        errores.append("Contraseña mínima de 6 caracteres.")
    return errores

@router.get("/registro", response_class=HTMLResponse)
def form_registro(request: Request):
    return templates.TemplateResponse("registro.html", {"request": request, "errores": []})

@router.post("/registro", response_class=HTMLResponse)
def guardar_registro(
    request: Request,
    nombre: str = Form(...),
    apellido: str = Form(...),
    dni: str = Form(...),
    email: str = Form(""),
    contrasena: str = Form(...),
):
    errores = validar(nombre, apellido, dni, email, contrasena)
    if errores:
        return templates.TemplateResponse(
            "registro.html",
            {"request": request, "errores": errores, "valores": request.form()},
        )

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO usuarios (nombre, apellido, dni, email, password) VALUES (?,?,?,?,?)",
        (nombre, apellido, dni, email, hash_password(contrasena)),
    )
    conn.commit()
    conn.close()
    # Redirect a página de inicio
    return RedirectResponse(url="/", status_code=303)
