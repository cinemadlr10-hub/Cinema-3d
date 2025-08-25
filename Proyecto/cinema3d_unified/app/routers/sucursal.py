
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from starlette.middleware.sessions import SessionMiddleware

templates = Jinja2Templates(directory="app/templates")

BRANCHES = ["Cine Pelagio B. Luna 960", "Cine San Martín 62"]

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    branch = request.session.get("branch")
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "branches": BRANCHES, "branch": branch},
    )

@router.post("/set-branch")
def set_branch(request: Request, branch: str = Form(...)):
    if branch not in BRANCHES:
        return JSONResponse({"ok": False, "msg": "Sucursal inválida"}, status_code=400)
    request.session["branch"] = branch
    return RedirectResponse(url="/cartelera", status_code=303)

@router.get("/clear-branch")
def clear_branch(request: Request):
    request.session.pop("branch", None)
    return RedirectResponse(url="/", status_code=303)
