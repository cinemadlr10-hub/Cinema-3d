# Cinema3D — Sprint 2 (HU03) — v2

Fix: reemplazo de filtro `| chr` en Jinja por `row_labels` generados en Python.

## Setup
```
python -m venv .venv
. .venv/Scripts/activate   # Windows
# source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
flask run
```
Abrir: http://127.0.0.1:5000/showtimes/TEST123/seats


# Cinema3D — Sprint 2 (HU03)

Solo incluye la HU03 (mapa de butacas + POST /reservations con lock en memoria).

## Requisitos
- Python 3.12+

## Setup rápido
```bash
python -m venv .venv
# Windows
. .venv/Scripts/activate
# Linux/macOS
# source .venv/bin/activate

pip install -r requirements.txt
flask run
```
> Si `flask` no está en PATH, usa: `python -m flask run`

Variables `.env` (ya creada):
```
FLASK_APP=app:create_app
FLASK_RUN_PORT=5000
BASE_URL=http://127.0.0.1:5000
RESERVATION_LOCK_TTL=600
```

Abrí: http://127.0.0.1:5000/showtimes/TEST123/seats

### Pruebas rápidas
Crear reserva:
```bash
curl -X POST http://127.0.0.1:5000/reservations   -H "Content-Type: application/json"   -d "{\"showtime_id\":\"TEST123\",\"seats\":[\"A3\",\"A4\"]}"
```
Si hay colisión devuelve 409 con `conflicted`.

### Notas
- El lock es en memoria (se pierde al reiniciar). Para demo del sprint está bien.
- El estado `locked` se purga automáticamente por TTL cuando se renderiza la vista o al crear reservas.
