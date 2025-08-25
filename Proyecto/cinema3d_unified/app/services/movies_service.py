from __future__ import annotations
from typing import List, Iterable
from datetime import datetime
from app.models import Movie, Showtime

def _match_genero(movie: Movie, genero: str | None) -> bool:
    return (genero is None) or (movie.genero.lower() == genero.lower())

def _match_query(movie: Movie, q: str | None) -> bool:
    if not q:
        return True
    query = q.lower()
    return query in movie.titulo.lower() or query in movie.sinopsis.lower()

def _filter_funciones(funciones: Iterable[Showtime], dia: str | None) -> List[Showtime]:
    if not dia:
        return list(funciones)
    try:
        target = datetime.strptime(dia, "%Y-%m-%d").date()
    except ValueError:
        return []
    return [f for f in funciones if f.fecha == target]

def filter_movies(movies: Iterable[Movie], genero: str | None, dia: str | None, q: str | None) -> List[Movie]:
    result: List[Movie] = []
    for m in movies:
        if not (_match_genero(m, genero) and _match_query(m, q)):
            continue
        funcs = _filter_funciones(m.funciones, dia)
        if dia and not funcs:
            # Si se filtró por día y la película no tiene funciones ese día, se excluye
            continue
        # Devolver una copia con solo las funciones filtradas (si aplica)
        copy = Movie(
            id=m.id,
            titulo=m.titulo,
            poster_url=m.poster_url,
            sinopsis=m.sinopsis,
            duracion_min=m.duracion_min,
            clasificacion=m.clasificacion,
            genero=m.genero,
            funciones=funcs if dia else m.funciones,
        )
        result.append(copy)
    # Orden alfabético por título
    return sorted(result, key=lambda x: x.titulo.lower())

def unique_genres(movies: Iterable[Movie]) -> List[str]:
    return sorted({m.genero for m in movies})
