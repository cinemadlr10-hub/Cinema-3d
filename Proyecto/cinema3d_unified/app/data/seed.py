from datetime import date, time
from app.models import Movie, Showtime

MOVIES = [
    Movie(
        id="m1",
        titulo="Nebula 9",
        poster_url="https://picsum.photos/seed/nebula9/300/450",
        sinopsis="Una misión a la estación Nebula 9 se complica cuando un fallo de IA amenaza la tripulación.",
        duracion_min=118,
        clasificacion="+13",
        genero="Ciencia Ficción",
        funciones=[
            Showtime(fecha=date.today(), hora=time(18, 30), sala="Sala 1"),
            Showtime(fecha=date.today(), hora=time(21, 0), sala="Sala 1"),
            Showtime(fecha=date.today().replace(day=min(28, date.today().day+1)), hora=time(19, 0), sala="Sala 2"),
        ],
    ),
    Movie(
        id="m2",
        titulo="Risas en la Oficina",
        poster_url="https://picsum.photos/seed/officefun/300/450",
        sinopsis="Una comedia sobre un equipo que intenta lanzar un producto en tiempo récord.",
        duracion_min=102,
        clasificacion="ATP",
        genero="Comedia",
        funciones=[
            Showtime(fecha=date.today(), hora=time(17, 0), sala="Sala 3"),
            Showtime(fecha=date.today().replace(day=min(28, date.today().day+2)), hora=time(20, 15), sala="Sala 3"),
        ],
    ),
    Movie(
        id="m3",
        titulo="Furia en la Ruta",
        poster_url="https://picsum.photos/seed/roadfury/300/450",
        sinopsis="Un piloto retirado vuelve a las pistas para una última carrera a través del desierto.",
        duracion_min=109,
        clasificacion="+16",
        genero="Acción",
        funciones=[
            Showtime(fecha=date.today(), hora=time(22, 0), sala="Sala 2"),
            Showtime(fecha=date.today().replace(day=min(28, date.today().day+3)), hora=time(22, 30), sala="Sala 2"),
        ],
    ),
]
