from pydantic import BaseModel, Field
from typing import List
from datetime import date, time

class Showtime(BaseModel):
    fecha: date
    hora: time
    sala: str = Field(default="Sala 1")

class Movie(BaseModel):
    id: str
    titulo: str
    poster_url: str
    sinopsis: str
    duracion_min: int
    clasificacion: str
    genero: str
    funciones: List[Showtime] = []
