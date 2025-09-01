"""HU03: mapa de butacas + reservas con lock en memoria (mejorado)."""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from string import ascii_uppercase
from typing import Iterable

from flask import Blueprint, current_app, jsonify, render_template, request

bp = Blueprint("reservations", __name__)

# Estructuras en memoria
# - _LOCKS[(showtime_id, seat)] = {"expires": int, "reservation_id": str}
# - _RESERVATIONS[reservation_id] = {"showtime_id": str, "seats": set[str], "expires": int}
_LOCKS: dict[tuple[str, str], dict] = {}
_RESERVATIONS: dict[str, dict] = {}

SEAT_ID_RE = re.compile(r"^[A-Z](?:[1-9]|[1-9][0-9])$")  # A1..A99


def _now() -> int:
    return int(time.time())


def _cfg_int(name: str, default: int) -> int:
    try:
        return int(current_app.config.get(name, default))
    except Exception:
        return default


def _root_dir() -> Path:
    # app.root_path -> .../app ; subimos un nivel al root del proyecto
    return Path(current_app.root_path).parent


def _data_dir() -> Path:
    return _root_dir() / "data"


def _purge_expired() -> None:
    """Eliminar locks/reservas vencidas."""
    now = _now()
    # 1) Purga por reserva
    expired_res = [rid for rid, meta in _RESERVATIONS.items() if meta["expires"] <= now]
    for rid in expired_res:
        meta = _RESERVATIONS.pop(rid, None)
        if not meta:
            continue
        sid = meta["showtime_id"]
        for s in list(meta["seats"]):
            _LOCKS.pop((sid, s), None)

    # 2) Purga por lock “huérfano” (seguridad)
    for key, meta in list(_LOCKS.items()):
        if meta["expires"] <= now or meta["reservation_id"] not in _RESERVATIONS:
            _LOCKS.pop(key, None)


def _seat_ids(rows: int = 10, cols: int = 12) -> Iterable[str]:
    labels = list(ascii_uppercase[:rows])
    for r in labels:
        for c in range(1, cols + 1):
            yield f"{r}{c}"


def _load_showtime(showtime_id: str) -> dict | None:
    data_path = _data_dir() / "showtimes.json"
    with data_path.open("r", encoding="utf-8") as f:
        shows = json.load(f)
    return next((s for s in shows if s["id"] == showtime_id), None)


def _load_occupied(showtime_id: str) -> set[str]:
    occupied_path = _data_dir() / f"seats_{showtime_id}.json"
    if occupied_path.exists():
        with occupied_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("ocupados", []))
    return set()


@bp.get("/showtimes/<showtime_id>/seats")
def seats_map(showtime_id: str):
    """Renderizar el mapa (HTML)."""
    _purge_expired()
    show = _load_showtime(showtime_id)
    if not show:
        return f"Showtime {showtime_id} no encontrado", 404

    rows, cols = 10, 12
    occupied = _load_occupied(showtime_id)
    now = _now()
    locked = {seat for (sid, seat), meta in _LOCKS.items() if sid == showtime_id and meta["expires"] > now}
    row_labels = list(ascii_uppercase[:rows])

    # Podés pasar MAX_SEATS a la vista si querés mostrarlo
    return render_template(
        "seats.html",
        show=show,
        rows=rows,
        cols=cols,
        row_labels=row_labels,
        occupied=occupied,
        locked=locked,
        max_seats=_cfg_int("MAX_SEATS_PER_RESERVATION", 6),
    )


@bp.get("/api/showtimes/<showtime_id>/seats")
def seats_state_api(showtime_id: str):
    """Estados en JSON para auto-refresh."""
    _purge_expired()
    show = _load_showtime(showtime_id)
    if not show:
        return jsonify(error="Showtime no encontrado"), 404

    rows, cols = 10, 12
    occupied = list(_load_occupied(showtime_id))
    now = _now()
    locked = [seat for (sid, seat), meta in _LOCKS.items() if sid == showtime_id and meta["expires"] > now]
    return jsonify(showtime_id=showtime_id, rows=rows, cols=cols, occupied=occupied, locked=locked, ts=now), 200


@bp.post("/reservations")
def create_reservation():
    """Crea una reserva (lock con TTL) y devuelve reservation_id."""
    _purge_expired()
    data = request.get_json(silent=True) or {}
    showtime_id = data.get("showtime_id", "").strip()
    seats = [str(s).upper().strip() for s in data.get("seats", []) if s]

    if not showtime_id or not seats:
        return jsonify(error="Faltan parámetros: showtime_id y seats[]"), 400

    # Validación de asientos
    invalid = [s for s in seats if not SEAT_ID_RE.match(s)]
    if invalid:
        return jsonify(error="Formato de asiento inválido", invalid=invalid), 400

    # Tope de asientos por reserva
    max_seats = _cfg_int("MAX_SEATS_PER_RESERVATION", 6)
    if len(seats) > max_seats:
        return jsonify(error=f"Máximo {max_seats} asientos por reserva"), 400

    show = _load_showtime(showtime_id)
    if not show:
        return jsonify(error=f"Showtime {showtime_id} no encontrado"), 404

    occupied = _load_occupied(showtime_id)
    ttl = _cfg_int("RESERVATION_LOCK_TTL", 600)
    now = _now()

    conflicted = []
    for s in seats:
        if s in occupied:
            conflicted.append(s)
        else:
            meta = _LOCKS.get((showtime_id, s))
            if meta and meta["expires"] > now:
                conflicted.append(s)

    if conflicted:
        return jsonify(error="Asientos no disponibles", conflicted=conflicted), 409

    # Crear reserva y locks
    expires = now + ttl
    reservation_id = f"R-{uuid.uuid4().hex[:8]}"
    _RESERVATIONS[reservation_id] = {"showtime_id": showtime_id, "seats": set(seats), "expires": expires}
    for s in seats:
        _LOCKS[(showtime_id, s)] = {"expires": expires, "reservation_id": reservation_id}

    return jsonify(
        reservation_id=reservation_id,
        showtime_id=showtime_id,
        seats=seats,
        ttl=ttl,
        expires_at=expires,
    ), 201


@bp.post("/reservations/release")
def release_reservation():
    """Liberar butacas de una reserva (todas o subset)."""
    _purge_expired()
    data = request.get_json(silent=True) or {}
    rid = data.get("reservation_id", "").strip()
    seats_req = data.get("seats")  # None -> todas

    meta = _RESERVATIONS.get(rid)
    if not meta:
        return jsonify(error="reservation_id inexistente o expirado"), 404

    sid = meta["showtime_id"]
    seats_to_release = set(seats_req) if seats_req else set(meta["seats"])

    released = []
    for s in list(seats_to_release):
        if s in meta["seats"]:
            meta["seats"].remove(s)
            _LOCKS.pop((sid, s), None)
            released.append(s)

    # Si no quedan asientos, eliminar la reserva
    if not meta["seats"]:
        _RESERVATIONS.pop(rid, None)

    return jsonify(reservation_id=rid, released=released), 200

@bp.get("/reservations")
def reservations_help():
    return {
        "message": "Usar POST con JSON: {showtime_id, seats[]}",
        "example": {"showtime_id": "TEST123", "seats": ["A3", "A4"]}
    }, 200
