import hashlib
import logging
import os
from contextlib import contextmanager
from typing import Any, Iterable, Optional

import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from psycopg2 import OperationalError, errors
from pydantic import BaseModel, EmailStr

PRIMARY_DB_HOST = os.getenv("PRIMARY_DB_HOST", os.getenv("DB_HOST", "db_primary"))
REPLICA_DB_HOST = os.getenv("REPLICA_DB_HOST", "db_replica")
DB_NAME = os.getenv("POSTGRES_DB", "auth_db")
DB_USER = os.getenv("POSTGRES_USER", "user_auth")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "password_auth")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:8080")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("simple_extractor.db")


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str


class TestItem(BaseModel):
    name: str
    description: Optional[str] = None


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(plain_password: str, stored_hash: str) -> bool:
    return hash_password(plain_password) == stored_hash


@contextmanager
def _connect(host: str):
    conn = psycopg2.connect(
        host=host,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )
    try:
        yield conn
    finally:
        conn.close()


def _run_query(
    target: str,
    query: str,
    params: Optional[Iterable[Any]] = None,
    fetch: str = "none",
):
    host = PRIMARY_DB_HOST if target == "primary" else REPLICA_DB_HOST
    label = "WRITE->primary" if target == "primary" else "READ->replica"
    params = params or ()

    try:
        with _connect(host) as conn:
            with conn.cursor() as cursor:
                logger.info("[%s] %s", label, " ".join(query.split()))
                cursor.execute(query, params)

                if target == "primary":
                    conn.commit()

                if fetch == "one":
                    return cursor.fetchone()
                if fetch == "all":
                    return cursor.fetchall()
                return None
    except OperationalError as exc:
        logger.exception("[%s] Error de conexion con la base de datos", label)
        raise HTTPException(
            status_code=503, detail="Servicio de base de datos no disponible."
        ) from exc


def run_read_query(query: str, params: Optional[Iterable[Any]] = None, fetch="all"):
    return _run_query("replica", query, params=params, fetch=fetch)


def run_write_query(query: str, params: Optional[Iterable[Any]] = None, fetch="none"):
    return _run_query("primary", query, params=params, fetch=fetch)


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
        run_read_query("SELECT 1", fetch="one")
    except HTTPException:
        db_status = "error"

    overall = "ok" if db_status == "ok" else "degraded"
    return {
        "status": overall,
        "services": {
            "database_read_replica": db_status,
        },
    }


@app.get("/api/users")
async def list_users():
    rows = run_read_query(
        "SELECT id, username, email, created_at FROM users ORDER BY id DESC",
        fetch="all",
    )
    return {
        "read_from": "replica",
        "users": [
            {
                "id": row[0],
                "username": row[1],
                "email": row[2],
                "created_at": row[3],
            }
            for row in rows or []
        ],
    }


@app.post("/api/users")
async def create_user(payload: UserCreate):
    hashed_password = hash_password(payload.password)
    try:
        row = run_write_query(
            """
            INSERT INTO users (username, email, password_hash)
            VALUES (%s, %s, %s)
            RETURNING id, username, email, created_at
            """,
            (payload.username, payload.email, hashed_password),
            fetch="one",
        )
    except errors.UniqueViolation as exc:
        raise HTTPException(
            status_code=409, detail="El usuario o el email ya existe."
        ) from exc

    return {
        "write_to": "primary",
        "user": {
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "created_at": row[3],
        },
    }


@app.post("/api/login")
async def login(payload: LoginRequest):
    try:
        user = run_read_query(
            """
            SELECT id, username, password_hash FROM users
            WHERE username = %s
            """,
            (payload.username,),
            fetch="one",
        )

        if not user or not verify_password(payload.password, user[2]):
            raise HTTPException(status_code=401, detail="Credenciales inválidas")

        return {"message": "Inicio de sesión exitoso", "user": {"id": user[0], "username": user[1]}}

    except Exception as exc:
        logger.exception("Error en el inicio de sesión")
        raise HTTPException(status_code=500, detail="Error en el servidor") from exc


# Endpoints de prueba
@app.post("/test-items/")
async def create_test_item(item: TestItem):
    try:
        # Insertar en la base de datos primaria
        result = run_write_query(
            """
            INSERT INTO test_items (name, description)
            VALUES (%s, %s)
            RETURNING id, name, description, created_at
            """,
            (item.name, item.description),
            fetch="one"
        )
        
        return {
            "message": "Item creado exitosamente",
            "item": {
                "id": result[0],
                "name": result[1],
                "description": result[2],
                "created_at": result[3].isoformat()
            }
        }
    except Exception as exc:
        logger.exception("Error al crear el ítem de prueba")
        raise HTTPException(status_code=500, detail="Error al crear el ítem") from exc


@app.get("/test-items/")
async def list_test_items():
    try:
        # Leer de la réplica
        items = run_read_query(
            """
            SELECT id, name, description, created_at
            FROM test_items
            ORDER BY created_at DESC
            """,
            fetch="all"
        )
        
        return {
            "items": [
                {
                    "id": item[0],
                    "name": item[1],
                    "description": item[2],
                    "created_at": item[3].isoformat()
                }
                for item in items
            ]
        }
    except Exception as exc:
        logger.exception("Error al listar los ítems de prueba")
        raise HTTPException(status_code=500, detail="Error al obtener los ítems") from exc
