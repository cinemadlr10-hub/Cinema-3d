
from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(__name__)

@app.template_filter("ars")
def ars(value):
    try:
        return f"${int(value):,}".replace(",", ".")
    except Exception:
        return value
import os
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-only-change-me")  # Needed for session

# --- Datos de ejemplo (podrías mover a BD luego) ---
COMBOS = [
    {"id": 1, "nombre": "Combo Clásico", "descripcion": "Pochoclos medianos + Gaseosa 500ml", "precio": 4500},
    {"id": 2, "nombre": "Combo Dúo", "descripcion": "Pochoclos grandes + 2 Gaseosas 500ml", "precio": 8200},
    {"id": 3, "nombre": "Combo Dulce", "descripcion": "Pochoclos caramelizados + Agua saborizada", "precio": 5200},
    {"id": 4, "nombre": "Combo Familiar", "descripcion": "Pochoclos XL + 4 Gaseosas 500ml", "precio": 12500},
    {"id": 5, "nombre": "Combo Estudiante", "descripcion": "Pochoclos chicos + Gaseosa 500ml + Golosina..", "precio": 3900},
    {"id": 6, "nombre": "Combo Cumpleaños", "descripcion": "Pochoclos grandes + 2 Gaseosas 500ml + 2 Golosinas.", "precio": 9500}
]


PRODUCTOS = [
    {"id": "bebida_coca_500", "nombre": "Coca-Cola 500 ml", "descripcion": "Gaseosa", "precio": 1200, "categoria": "Bebidas"},
    {"id": "bebida_agua_500", "nombre": "Agua mineral 500 ml", "descripcion": "Sin gas", "precio": 900, "categoria": "Bebidas"},
    {"id": "bebida_sprite_500", "nombre": "Sprite 500 ml", "descripcion": "Gaseosa lima-limón", "precio": 1200, "categoria": "Bebidas"},
    {"id": "bebida_fanta_500", "nombre": "Fanta 500 ml", "descripcion": "Gaseosa naranja", "precio": 1200, "categoria": "Bebidas"},
    {"id": "bebida_agua_saborizada", "nombre": "Agua saborizada 500 ml", "descripcion": "Sabor pomelo", "precio": 1100, "categoria": "Bebidas"},
    {"id": "bebida_pepsi_500", "nombre": "Pepsi 500 ml", "descripcion": "Gaseosa", "precio": 1200, "categoria": "Bebidas"},

    {"id": "pocho_chico", "nombre": "Pochoclos Chico", "descripcion": "Porción individual", "precio": 1800, "categoria": "Pochoclos"},
    {"id": "pocho_grande", "nombre": "Pochoclos Grande", "descripcion": "Balde grande", "precio": 2500, "categoria": "Pochoclos"},
    {"id": "pocho_caramel", "nombre": "Pochoclos Caramelizados", "descripcion": "Dulces", "precio": 2200, "categoria": "Pochoclos"},
    {"id": "pocho_queso", "nombre": "Pochoclos sabor queso", "descripcion": "Saborizados", "precio": 2300, "categoria": "Pochoclos"},
    {"id": "pocho_manteca", "nombre": "Pochoclos a la manteca", "descripcion": "Clásicos con manteca", "precio": 2100, "categoria": "Pochoclos"},
    {"id": "pocho_picante", "nombre": "Pochoclos Salados", "descripcion": "Con toque de ají y especias", "precio": 2400, "categoria": "Pochoclos"},

    {"id": "golo_chocolate", "nombre": "Chocolate", "descripcion": "Tableta", "precio": 800, "categoria": "Golosinas"},
    {"id": "golo_caramelos", "nombre": "Caramelos", "descripcion": "Surtidos", "precio": 600, "categoria": "Golosinas"},
    {"id": "golo_gomitas", "nombre": "Gomitas", "descripcion": "Frutales", "precio": 950, "categoria": "Golosinas"},
    {"id": "golo_barra", "nombre": "Barra de cereal", "descripcion": "Avena y miel", "precio": 700, "categoria": "Golosinas"},
    {"id": "golo_alfajor", "nombre": "Alfajor", "descripcion": "Dulce de leche", "precio": 850, "categoria": "Golosinas"},
    {"id": "golo_turron", "nombre": "Turrón", "descripcion": "Maní y miel", "precio": 750, "categoria": "Golosinas"},
]


def _get_cart():
    cart = session.get("cart", {})
    # cart = { combo_id(str): cantidad(int) }
    return cart

def _save_cart(cart):
    session["cart"] = cart

def _calc_totals(cart):
    items = []
    total = 0
    for cid_str, qty in cart.items():
        # Combos
        try:
            cid = int(cid_str)
            combo = next((c for c in COMBOS if c["id"] == cid), None)
        except ValueError:
            combo = None
        if combo and qty > 0:
            subtotal = combo["precio"] * qty
            total += subtotal
            items.append({
                "id": cid,
                "nombre": combo["nombre"],
                "descripcion": combo["descripcion"],
                "precio": combo["precio"],
                "cantidad": qty,
                "subtotal": subtotal,
            })
        # Productos individuales
        prod = next((p for p in PRODUCTOS if p["id"] == cid_str), None)
        if prod and qty > 0:
            subtotal = prod["precio"] * qty
            total += subtotal
            items.append({
                "id": prod["id"],
                "nombre": prod["nombre"],
                "descripcion": prod["descripcion"],
                "precio": prod["precio"],
                "cantidad": qty,
                "subtotal": subtotal,
            })
    return items, total

@app.route("/")
def index():
    return redirect(url_for("listar_combos"))

# 1) Ver listado de combos disponibles.
@app.route("/combos", methods=["GET"])
def listar_combos():
    cart = _get_cart()
    print("[DEBUG] PRODUCTOS enviados al template:", PRODUCTOS)
    return render_template("combos.html", combos=COMBOS, productos=PRODUCTOS, cart=cart)

# 2) Seleccionar uno o varios combos (agregar al carrito / actualizar cantidades).
@app.route("/combos", methods=["POST"])
def agregar_actualizar_combos():
    # Se reciben pares combo_<id> con cantidad (puede ser 0).
    cart = {}
    # Combos
    for combo in COMBOS:
        field = f"combo_{combo['id']}"
        qty_str = request.form.get(field, "0").strip()
        try:
            qty = int(qty_str)
        except ValueError:
            qty = 0
        if qty < 0:
            qty = 0
        if qty > 0:
            cart[str(combo["id"])] = qty
        # Si qty es 0, no se agrega al carrito (se elimina si estaba)
    # Productos individuales
    for prod in PRODUCTOS:
        qty_str = request.form.get(prod["id"], "0").strip()
        try:
            qty = int(qty_str)
        except ValueError:
            qty = 0
        if qty < 0:
            qty = 0
        if qty > 0:
            cart[prod["id"]] = qty
        # Si qty es 0, no se agrega al carrito (se elimina si estaba)

    _save_cart(cart)
    flash("Carrito actualizado.", "success")
    return redirect(url_for("ver_carrito"))

# 3) Sumar al precio total de la compra (ver carrito / total).
@app.route("/carrito", methods=["GET", "POST"])
def ver_carrito():
    cart = _get_cart()

    if request.method == "POST":
        # Eliminar un ítem si se presionó el botón de eliminar
        del_item = request.form.get("del_item")
        if del_item:
            cart.pop(del_item, None)
            _save_cart(cart)
            flash(f"Producto '{del_item}' eliminado del carrito.", "info")
            return redirect(url_for("ver_carrito"))
        action = request.form.get("action")
        if action == "vaciar":
            cart = {}
            _save_cart(cart)
            flash("Carrito vaciado.", "info")
            return redirect(url_for("listar_combos"))
        elif action == "actualizar":
            # Actualizar cantidades desde el carrito
            new_cart = {}
            for combo in COMBOS:
                field = f"qty_{combo['id']}"
                qty_str = request.form.get(field, "0").strip()
                try:
                    qty = int(qty_str)
                except ValueError:
                    qty = 0
                if qty > 0:
                    new_cart[str(combo["id"])] = qty
            # Productos individuales
            for prod in PRODUCTOS:
                field = f"qty_{prod['id']}"
                qty_str = request.form.get(field, "0").strip()
                try:
                    qty = int(qty_str)
                except ValueError:
                    qty = 0
                if qty > 0:
                    new_cart[prod["id"]] = qty
            _save_cart(new_cart)
            flash("Cantidades actualizadas.", "success")
            return redirect(url_for("ver_carrito"))

    items, total = _calc_totals(cart)
    return render_template("cart.html", items=items, total=total)


# === Sección de Productos (Bebidas, Pochoclos, Golosinas) ===
@app.route("/productos", methods=["GET", "POST"])
def listar_productos():
    cart = _get_cart()
    if request.method == "POST":
        # Actualizar cantidades de productos individuales
        new_cart = dict(cart)
        for p in PRODUCTOS:
            field = f"prod_{p['id']}"
            qty_str = request.form.get(field, "0").strip()
            try:
                qty = int(qty_str)
            except ValueError:
                qty = 0
            if qty <= 0:
                new_cart.pop(p["id"], None)
            else:
                new_cart[p["id"]] = qty
        _save_cart(new_cart)
        flash("Productos actualizados en el carrito.", "success")
        return redirect(url_for("ver_carrito"))

    # Agrupar por categoría
    categorias = ["Bebidas", "Pochoclos", "Golosinas"]
    por_categoria = {c: [p for p in PRODUCTOS if p.get("categoria")==c] for c in categorias}
    return render_template("products.html", por_categoria=por_categoria, cart=cart)


if __name__ == "__main__":
    app.run(debug=True)
