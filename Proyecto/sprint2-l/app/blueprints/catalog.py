from __future__ import annotations
from flask import Blueprint, render_template
import json, os

bp = Blueprint("catalog", __name__)

def _data_dir():
    here = os.path.dirname(__file__)
    return os.path.join(os.path.dirname(os.path.dirname(here)), "data")

@bp.get("/cartelera")
def cartelera():
    with open(os.path.join(_data_dir(), "movies.json"), "r", encoding="utf-8") as f:
        movies = json.load(f)
    with open(os.path.join(_data_dir(), "showtimes.json"), "r", encoding="utf-8") as f:
        showtimes = json.load(f)
    by_movie = {}
    for st in showtimes:
        by_movie.setdefault(st["movie_id"], []).append(st)
    return render_template("catalog/cartelera.html", movies=movies, showtimes_by_movie=by_movie)
