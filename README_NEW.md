# SimpleExtractor

Aplicacion web para extraer y analizar texto de imagenes, con autenticacion y base de datos PostgreSQL empaquetada en contenedores.

## Caracteristicas
- Extraccion de texto de imagenes
- Autenticacion de usuarios con hash SHA-256
- API RESTful en FastAPI
- Frontend estatico (HTML/JS/CSS)
- Contenedores con Docker y Docker Compose
- Replica de base de datos para separar lecturas (GET) hacia la replica y escrituras (POST/PUT/DELETE) hacia la primaria, con logs de evidencia

## Tecnologias
- Backend: Python (FastAPI), psycopg2
- Frontend: HTML, JavaScript, CSS
- Base de datos: PostgreSQL
- Contenedores: Docker y Docker Compose
- Procesamiento de imagenes: bibliotecas de procesamiento de imagenes

## Arquitectura de base de datos (primaria + replica)
- `db_primary` (puerto 5432): instancia principal; acepta escrituras y crea usuario de replicacion.
- `db_replica` (puerto 5433): standby creada con `pg_basebackup`, configurada para `hot_standby=on`.
- El backend abre dos pools logicos: lecturas via `READ->replica` y escrituras via `WRITE->primary` (observables en los logs del contenedor `backend`).

## Estructura del proyecto
```
.
├── backend/
│   ├── main.py              # API FastAPI (lecturas a replica, escrituras a primaria)
│   └── requirements.txt
├── db/
│   ├── init/
│   │   ├── 00-replication.sh    # Crea rol de replicacion y habilita pg_hba
│   │   └── 01-init.sql          # Esquema de usuarios
│   └── replica/
│       └── replica-entrypoint.sh # Clona la primaria y arranca la replica
├── frontend/
│   ├── Extractor/
│   └── index.html
├── docker-compose.yml
└── .gitignore
```

## Variables de entorno (ejemplo `.env`)
```
POSTGRES_USER=user_auth
POSTGRES_PASSWORD=password_auth
POSTGRES_DB=auth_db
FRONTEND_ORIGIN=http://localhost:8080

# Hosts usados por el backend (coinciden con docker-compose)
PRIMARY_DB_HOST=db_primary
REPLICA_DB_HOST=db_replica

# Credenciales de replicacion usadas por la primaria/replica
REPLICATION_USER=replicator
REPLICATION_PASSWORD=replicator_password
```

## Puesta en marcha
1) Instala Docker y Docker Compose.  
2) Levanta los servicios:
```bash
docker compose up --build
# o: docker-compose up --build
```
3) Accede:
- Frontend: http://localhost:8080
- API: http://localhost:8000
- PostgreSQL primaria: localhost:5432
- PostgreSQL replica: localhost:5433

> Si cambiaste de la version previa con una sola base, elimina volumnes previos antes de levantar (`docker compose down -v`) para que se regenere la primaria y la replica.

## Endpoints clave y evidencia de lectura/escritura
- `GET /api/users` -> lee la replica (`read_from: replica` en la respuesta) y log `[READ->replica]`.
- `POST /api/users` -> escribe en la primaria (`write_to: primary` en la respuesta) y log `[WRITE->primary]`.
- `POST /api/login` -> valida credenciales leyendo en la replica.
- `GET /healthz` -> comprueba conectividad de la replica.

Ver logs para evidenciar la separacion:
```bash
docker compose logs -f backend | grep "READ->replica"
docker compose logs -f backend | grep "WRITE->primary"
```

## Testing
```bash
# Instalar dependencias de prueba (opcional)
pip install -r requirements-test.txt

# Ejecutar pruebas
pytest
```

## Contribucion
1. Fork del proyecto
2. Rama de feature (`git checkout -b feature/mi-feature`)
3. Commit (`git commit -m "feat: mi cambio"`)
4. Push (`git push origin feature/mi-feature`)
5. Pull Request

## Licencia
MIT (ver archivo LICENSE).

## Contacto
Proyecto creado por [Tu Nombre] - [@tuusuario](https://github.com/tuusuario)
