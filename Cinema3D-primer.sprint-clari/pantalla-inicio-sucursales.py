from flask import Flask, render_template, request, session, jsonify

app = Flask(__name__)
app.secret_key = "cambia-esto"  # pon un valor seguro

BRANCHES = ["Cine Pelagio B. Luna 960", "Cine San Martín 62"]
@app.route("/")
def index():
    return render_template("index.html", branches=BRANCHES, branch=session.get("branch"))

@app.post("/set-branch")
def set_branch():
    data = request.get_json() or request.form
    branch = (data.get("branch") or "").strip()
    if branch not in BRANCHES:
        return jsonify(ok=False, error="Sucursal inválida"), 400
    session["branch"] = branch
    return jsonify(ok=True, branch=branch)

@app.post("/clear-branch")
def clear_branch():
    session.pop("branch", None)
    return jsonify(ok=True)

if __name__ == "__main__":
    app.run(debug=True)
