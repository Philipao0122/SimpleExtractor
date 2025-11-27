# Guía rápida de base de datos

Esta referencia explica cómo levantar el entorno, conectarte al contenedor de PostgreSQL, consultar la tabla `users` e insertar registros desde la terminal.

## 1. Levantar los servicios

```powershell
# Desde la raíz del proyecto
docker-compose up --build
```

Esto creará tres contenedores:
- **db**: PostgreSQL 14 con la tabla `users` definida en `db/init/01-init.sql`.
- **backend**: API FastAPI que valida usuarios contra la base.
- **frontend**: Sitio estático Tailwind que consume la API.

Cuando veas `database system is ready to accept connections` en los logs de `db`, puedes conectarte.

## 2. Conectarse al contenedor de PostgreSQL

Abre otra terminal y ejecuta:

```powershell
docker-compose exec db psql -U user_auth -d auth_db
```

Esto abre el prompt interactivo de `psql`. Para salir escribe `\q`.

## 3. Consultar usuarios existentes

Una vez dentro de `psql`, ejecuta:

```sql
SELECT id, username, email, password_hash, created_at FROM users ORDER BY id;
```

> Nota: `password_hash` guarda el hash SHA-256 de la contraseña en texto plano.

## 4. Insertar usuarios manualmente desde `psql`

1. Genera el hash SHA-256 de la contraseña. Puedes hacerlo con Python en tu máquina:
   ```powershell
   python - <<'PY'
   import hashlib
   plain = "mi_contrasena_segura"
   print(hashlib.sha256(plain.encode()).hexdigest())
   PY
   ```
2. Copia el hash resultante e insértalo en la tabla:
   ```sql
   INSERT INTO users (username, email, password_hash)
   VALUES ('nuevo_usuario', 'nuevo@example.com', 'HASH_OBTENIDO');
   ```
   Si el `username` ya existe, utiliza `INSERT ... ON CONFLICT`:
   ```sql
   INSERT INTO users (username, email, password_hash)
   VALUES ('nuevo_usuario', 'nuevo@example.com', 'HASH_OBTENIDO')
   ON CONFLICT (username)
   DO UPDATE SET email = EXCLUDED.email, password_hash = EXCLUDED.password_hash;
   ```

## 5. Insertar usuarios con el script `insert_users.py`

El repositorio incluye `scripts/insert_users.py`, que ya maneja el hashing y los "upserts".

1. Instala dependencias locales (una sola vez):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r scripts\requirements.txt
   ```
2. Ejecuta el script (con los servicios levantados):
   ```powershell
   python scripts\insert_users.py
   ```
   Verás mensajes confirmando que `alice_smith`, `bob_jones` y `charlie_brown` fueron insertados/actualizados.

> También puedes ejecutar el script desde un contenedor efímero que comparta red con `db`:
> ```powershell
> docker run --rm -v ${PWD}:/app -w /app --network=docker-auth-project_default \
>     python:3.11-slim bash -c "pip install -r scripts/requirements.txt && python scripts/insert_users.py"
> ```
> Asegúrate de reemplazar `docker-auth-project_default` por la red real que crea Docker Compose.

## 6. Verificar inserciones

Ejecuta nuevamente el `SELECT` del paso 3 o usa la API:

```powershell
curl -X POST http://localhost:8000/api/login \
     -H "Content-Type: application/json" \
     -d '{"username":"alice_smith","password":"alice123"}'
```

Un `200 OK` confirmará que la API y la base comparten los mismos datos.
