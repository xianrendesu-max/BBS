import os, secrets
from fastapi import FastAPI, Request, Form, Header
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker, declarative_base

# ===== 環境変数 =====
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "sennin252519192323")
DATABASE_URL = "sqlite:////data/bbs.db"

# ===== DB =====
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password = Column(String)
    is_admin = Column(Integer, default=0)
    api_key = Column(String)

class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True)
    user = Column(String)
    content = Column(Text)
    likes = Column(Integer, default=0)
    is_admin = Column(Integer, default=0)
    pinned = Column(Integer, default=0)

Base.metadata.create_all(bind=engine)

# ===== APP =====
app = FastAPI(debug=False)
templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

# ===== ルート =====
@app.get("/")
def root():
    return RedirectResponse("/login")

# ===== 一般ユーザー =====
@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    db = get_db()
    user = db.query(User).filter_by(username=username, password=password).first()
    if not user:
        return HTMLResponse("ログイン失敗")
    res = RedirectResponse("/board", 302)
    res.set_cookie("user", user.username, httponly=True, samesite="lax", secure=True)
    res.set_cookie("admin", "0", httponly=True, samesite="lax", secure=True)
    return res

@app.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
def register(username: str = Form(...), password: str = Form(...)):
    db = get_db()
    if db.query(User).filter_by(username=username).first():
        return HTMLResponse("既に存在します")
    db.add(User(username=username, password=password))
    db.commit()
    return RedirectResponse("/login", 302)

# ===== 管理者ログイン =====
@app.get("/admin_login")
def admin_login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})

@app.post("/admin_login")
def admin_login(username: str = Form(...), password: str = Form(...)):
    if username != "admin" or password != ADMIN_PASSWORD:
        return HTMLResponse("失敗")
    db = get_db()
    admin = db.query(User).filter_by(username="admin").first()
    if not admin:
        admin = User(
            username="admin",
            password="",
            is_admin=1,
            api_key=secrets.token_hex(24)
        )
        db.add(admin)
        db.commit()
    res = RedirectResponse("/admin", 302)
    res.set_cookie("user", "admin", httponly=True, samesite="lax", secure=True)
    res.set_cookie("admin", "1", httponly=True, samesite="lax", secure=True)
    return res

# ===== 掲示板 =====
@app.get("/board")
def board(request: Request):
    db = get_db()
    posts = db.query(Post).order_by(Post.pinned.desc(), Post.id.desc()).all()
    return templates.TemplateResponse(
        "board.html",
        {
            "request": request,
            "posts": posts,
            "user": request.cookies.get("user"),
            "is_admin": request.cookies.get("admin") == "1"
        }
    )

@app.post("/post")
def post(request: Request, content: str = Form(...)):
    if len(content) > 500:
        return HTMLResponse("長すぎます")
    db = get_db()
    db.add(Post(
        user=request.cookies.get("user"),
        content=content,
        is_admin=1 if request.cookies.get("admin") == "1" else 0
    ))
    db.commit()
    return RedirectResponse("/board", 302)

@app.post("/like/{pid}")
def like(pid: int):
    db = get_db()
    p = db.query(Post).get(pid)
    if p:
        p.likes += 1
        db.commit()
    return RedirectResponse("/board", 302)

# ===== 管理者 =====
@app.get("/admin")
def admin_page(request: Request):
    if request.cookies.get("admin") != "1":
        return HTMLResponse("権限なし")
    db = get_db()
    admin = db.query(User).filter_by(username="admin").first()
    posts = db.query(Post).order_by(Post.id.desc()).all()
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "posts": posts, "api_key": admin.api_key}
    )

@app.post("/admin/delete/{pid}")
def admin_delete(pid: int, request: Request):
    if request.cookies.get("admin") != "1":
        return HTMLResponse("権限なし")
    db = get_db()
    p = db.query(Post).get(pid)
    if p:
        db.delete(p)
        db.commit()
    return RedirectResponse("/admin", 302)

@app.post("/admin/pin/{pid}")
def admin_pin(pid: int, request: Request):
    if request.cookies.get("admin") != "1":
        return HTMLResponse("権限なし")
    db = get_db()
    p = db.query(Post).get(pid)
    if p:
        p.pinned = 0 if p.pinned else 1
        db.commit()
    return RedirectResponse("/admin", 302)

# ===== 管理者API =====
@app.get("/api/admin/posts")
def admin_api(x_api_key: str = Header(None)):
    db = get_db()
    admin = db.query(User).filter_by(api_key=x_api_key, is_admin=1).first()
    if not admin:
        return {"error": "unauthorized"}
    return [
        {"id": p.id, "user": p.user, "content": p.content, "likes": p.likes}
        for p in db.query(Post).all()
    ]
