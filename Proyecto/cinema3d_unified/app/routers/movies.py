from fastapi import APIRouter, Query
from typing import List
from app.models import Movie
from app.data.seed import MOVIES
from app.services.movies_service import filter_movies

router = APIRouter()

@router.get("/peliculas", response_model=List[Movie])
def get_peliculas(
    genero: str | None = Query(None, description="Género exacto, p. ej. 'Acción'"),
    dia: str | None = Query(None, description="Fecha YYYY-MM-DD"),
    q: str | None = Query(None, description="Búsqueda en título o sinopsis"),
):
    return filter_movies(MOVIES, genero=genero, dia=dia, q=q)
