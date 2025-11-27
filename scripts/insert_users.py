import hashlib
import os
import time

import psycopg2

# Configuración de la conexión a la base de datos
DB_HOST = os.environ.get("DB_HOST", "db")
DB_NAME = os.environ.get("POSTGRES_DB", "auth_db")
DB_USER = os.environ.get("POSTGRES_USER", "user_auth")
DB_PASS = os.environ.get("POSTGRES_PASSWORD", "password_auth")

# Datos de usuarios a insertar (password en texto plano, se almacenará hasheado)
USERS_TO_INSERT = [
    ("juan", "juan@example.com", "prueba123")
    
]


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def insert_users():
    """
    Se conecta a la base de datos PostgreSQL e inserta usuarios.
    """
    conn = None
    max_retries = 10
    retry_delay = 5  # segundos

    for attempt in range(max_retries):
        try:
            print(f"Intentando conectar a la base de datos... Intento {attempt + 1}/{max_retries}")
            # Conexión a la base de datos
            conn = psycopg2.connect(
                host=DB_HOST,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASS
            )
            cursor = conn.cursor()

            # Consulta SQL para la inserción
            insert_query = """
            INSERT INTO users (username, email, password_hash)
            VALUES (%s, %s, %s)
            ON CONFLICT (username)
            DO UPDATE SET
                email = EXCLUDED.email,
                password_hash = EXCLUDED.password_hash;
            """

            # Insertar cada usuario
            for username, email, plain_password in USERS_TO_INSERT:
                hashed_password = hash_password(plain_password)
                cursor.execute(insert_query, (username, email, hashed_password))
                print(f"Usuario '{username}' insertado/actualizado.")

            # Confirmar la transacción
            conn.commit()
            print("Inserción de usuarios completada con éxito.")
            break  # Salir del bucle si la conexión fue exitosa

        except psycopg2.OperationalError as e:
            print(f"Error de conexión a la base de datos: {e}")
            if attempt < max_retries - 1:
                print(f"Esperando {retry_delay} segundos antes de reintentar...")
                time.sleep(retry_delay)
            else:
                print("Máximo de reintentos alcanzado. Fallo al conectar a la base de datos.")
                raise
        except Exception as e:
            print(f"Ocurrió un error: {e}")
            raise
        finally:
            # Cerrar la conexión
            if conn:
                conn.close()

if __name__ == "__main__":
    insert_users()
