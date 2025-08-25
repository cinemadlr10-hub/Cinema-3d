
# CINEMA3D — Proyecto Unificado (Sprint 1)

Este repositorio integra **tres módulos originales** en **un solo servidor FastAPI**:

1. **Selección de Sucursal** (`Cinema3D.zip`)
2. **Registro de Usuarios** (`cine_web.zip`)
3. **HU01 Cartelera con filtros** (`cinema3d_fastapi_prototype.zip`)

## Funcionalidades
| Ruta | Descripción |
|------|-------------|
| `/` | Página de inicio. Elige la sucursal. Incluye botón **Registrarse** |
| `/registro` | Formulario de registro (diseño original). Valida y guarda en **SQLite** |
| `/cartelera` | Cartelera filtrable por género, día y búsqueda |
| `/api/peliculas` | API JSON de películas (mismos filtros) |

## Tecnologías
- **FastAPI** + **Uvicorn** (ASGI)
- **Jinja2** para las vistas
- **SessionMiddleware** para almacenar la sucursal
- **SQLite** para usuarios (hash PBKDF2-SHA256 demo)

## Ejecutar
```powershell
cd cinema3d_unified
python -m venv .venv
py -m venv .venv
# PowerShell
.\.venv\Scripts\Activate.ps1
# bash/cmd ➜ source .venv/bin/activate  |  .venv\Scripts\activate.bat
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Abre:

* `http://127.0.0.1:8000/` — Inicio  
* `http://127.0.0.1:8000/cartelera` — Cartelera  
* `http://127.0.0.1:8000/registro` — Registro  

## Estructura
```
app/
  data/seed.py
  models.py
  routers/
    movies.py
    registro.py
    sucursal.py
  services/
    movies_service.py
  templates/
    index.html
    registro.html
    cartelera.html
  static/css/styles.css
  main.py
requirements.txt
README.md
```
