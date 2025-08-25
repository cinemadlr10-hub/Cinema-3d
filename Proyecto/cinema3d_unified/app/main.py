
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from app.routers.movies import router as movies_router
from app.routers.registro import router as registro_router
from app.routers.sucursal import router as sucursal_router

app = FastAPI(title="CINEMA3D Unificado", version="0.2.0")

# Session (secreta, demo)
app.add_middleware(SessionMiddleware, secret_key="cambia-esto-por-env")

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Routers
app.include_router(sucursal_router)          # /, /set-branch
app.include_router(movies_router, prefix="/api", tags=["cartelera"])
app.include_router(registro_router)          # /registro

# Import templates for /cartelera (mantener logica UI)
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi import Request, Query
from app.services.movies_service import filter_movies, unique_genres
from app.data.seed import MOVIES

templates = Jinja2Templates(directory="app/templates")

@app.get("/cartelera", response_class=HTMLResponse)
def cartelera(
    request: Request,
    genero: str | None = Query(None),
    dia: str | None = Query(None),
    q: str | None = Query(None),
):
    peliculas = filter_movies(MOVIES, genero, dia, q)
    genres = unique_genres(MOVIES)
    branch = request.session.get("branch")
    return templates.TemplateResponse(
        "cartelera.html",
        {
            "request": request,
            "movies": peliculas,
            "genres": genres,
            "genero": genero or "",
            "dia": dia or "",
            "q": q or "",
            "branch": branch,
        },
    )

