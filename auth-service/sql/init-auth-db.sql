-- SQL script para crear la base de datos separada de auth-service
-- sql/init-auth-db.sql

-- Crear base de datos para auth-service (separada de Guacamole)
CREATE DATABASE IF NOT EXISTS auth_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Crear usuario específico para auth-service
CREATE USER IF NOT EXISTS 'auth_user'@'%' IDENTIFIED BY 'secure_auth_password';

-- Otorgar permisos completos en la base de datos auth_db
GRANT ALL PRIVILEGES ON auth_db.* TO 'auth_user'@'%';

-- Aplicar cambios
FLUSH PRIVILEGES;

-- Crear tabla para cache de keys (opcional, JPA puede crearla automáticamente)
USE auth_db;

CREATE TABLE IF NOT EXISTS public_key_cache (
    id VARCHAR(255) PRIMARY KEY,
    public_key TEXT NOT NULL,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    INDEX idx_expires_at (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tabla para logs de autenticación (opcional)
CREATE TABLE IF NOT EXISTS auth_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_address VARCHAR(42) NOT NULL,
    endpoint VARCHAR(255) NOT NULL,
    success BOOLEAN NOT NULL,
    error_message TEXT NULL,
    ip_address VARCHAR(45) NULL,
    user_agent TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_address (user_address),
    INDEX idx_created_at (created_at),
    INDEX idx_success (success)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;