-- Crea la tabla de usuarios
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Crea un índice para búsquedas rápidas por nombre de usuario
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users (username);

-- Crea un índice para búsquedas rápidas por email
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users (email);
