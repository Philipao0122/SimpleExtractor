import hashlib
import os
from contextlib import contextmanager

import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from psycopg2 import OperationalError
from pydantic import BaseModel

DB_HOST = os.getenv("DB_HOST", "db")
DB_NAME = os.getenv("POSTGRES_DB", "auth_db")
DB_USER = os.getenv("POSTGRES_USER", "user_auth")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "password_auth")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:8080")


@contextmanager
def get_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )
    try:
        yield conn
    finally:
        conn.close()


class LoginRequest(BaseModel):
    username: str
    password: str


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(plain_password: str, stored_hash: str) -> bool:
    return hash_password(plain_password) == stored_hash


app = FastAPI(title="Docker Auth API")

default_origins = {
    FRONTEND_ORIGIN.rstrip("/"),
    "http://localhost",
    "http://localhost:8080",
    "http://127.0.0.1",
    "http://127.0.0.1:8080",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in default_origins if origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthcheck():
    db_status = "ok"
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
    except OperationalError:
        db_status = "error"

    overall = "ok" if db_status == "ok" else "degraded"
    return {
        "status": overall,
        "services": {
            "database": db_status,
        },
    }


@app.post("/api/login")
async def login(payload: LoginRequest):
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT username, email, password_hash FROM users WHERE username = %s",
                    (payload.username,),
                )
                row = cursor.fetchone()
    except OperationalError as exc:
        raise HTTPException(
            status_code=503, detail="Servicio de base de datos no disponible."
        ) from exc

    if not row:
        raise HTTPException(status_code=401, detail="Usuario o contraseña inválidos.")

    stored_username, stored_email, stored_password_hash = row

    if not verify_password(payload.password, stored_password_hash):
        raise HTTPException(status_code=401, detail="Usuario o contraseña inválidos.")

    return {
        "message": "Autenticación exitosa",
        "user": {
            "username": stored_username,
            "email": stored_email,
        },
    }
