-- Auth Service Database Schema
-- Tables for blockchain-based authentication and lab reservations

-- Table for storing user authentication data
CREATE TABLE IF NOT EXISTS `auth_users` (
  `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
  `wallet_address` VARCHAR(42) NOT NULL UNIQUE,
  `username` VARCHAR(128),
  `email` VARCHAR(256),
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `is_active` BOOLEAN DEFAULT TRUE,
  
  INDEX `idx_wallet_address` (`wallet_address`),
  INDEX `idx_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Table for storing JWT tokens and their metadata
CREATE TABLE IF NOT EXISTS `jwt_tokens` (
  `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
  `jti` VARCHAR(128) NOT NULL UNIQUE,
  `user_id` BIGINT NOT NULL,
  `wallet_address` VARCHAR(42) NOT NULL,
  `issued_at` TIMESTAMP NOT NULL,
  `expires_at` TIMESTAMP NOT NULL,
  `revoked` BOOLEAN DEFAULT FALSE,
  `revoked_at` TIMESTAMP NULL,
  `ip_address` VARCHAR(45),
  `user_agent` TEXT,
  
  INDEX `idx_jti` (`jti`),
  INDEX `idx_user_id` (`user_id`),
  INDEX `idx_wallet_address` (`wallet_address`),
  INDEX `idx_expires_at` (`expires_at`),
  INDEX `idx_revoked` (`revoked`),
  
  FOREIGN KEY (`user_id`) REFERENCES `auth_users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Table for storing lab reservations from smart contracts
CREATE TABLE IF NOT EXISTS `lab_reservations` (
  `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
  `transaction_hash` VARCHAR(66) NOT NULL UNIQUE,
  `user_id` BIGINT NOT NULL,
  `wallet_address` VARCHAR(42) NOT NULL,
  `lab_id` VARCHAR(128) NOT NULL,
  `start_time` TIMESTAMP NOT NULL,
  `end_time` TIMESTAMP NOT NULL,
  `block_number` BIGINT,
  `contract_address` VARCHAR(42),
  `status` ENUM('PENDING', 'CONFIRMED', 'ACTIVE', 'COMPLETED', 'CANCELLED') DEFAULT 'PENDING',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  
  INDEX `idx_transaction_hash` (`transaction_hash`),
  INDEX `idx_user_id` (`user_id`),
  INDEX `idx_wallet_address` (`wallet_address`),
  INDEX `idx_lab_id` (`lab_id`),
  INDEX `idx_start_time` (`start_time`),
  INDEX `idx_status` (`status`),
  
  FOREIGN KEY (`user_id`) REFERENCES `auth_users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Table for storing authentication sessions
CREATE TABLE IF NOT EXISTS `auth_sessions` (
  `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
  `session_id` VARCHAR(128) NOT NULL UNIQUE,
  `user_id` BIGINT NOT NULL,
  `wallet_address` VARCHAR(42) NOT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `last_accessed` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `expires_at` TIMESTAMP NOT NULL,
  `ip_address` VARCHAR(45),
  `user_agent` TEXT,
  `is_active` BOOLEAN DEFAULT TRUE,
  
  INDEX `idx_session_id` (`session_id`),
  INDEX `idx_user_id` (`user_id`),
  INDEX `idx_expires_at` (`expires_at`),
  INDEX `idx_is_active` (`is_active`),
  
  FOREIGN KEY (`user_id`) REFERENCES `auth_users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Table for storing nonces used in wallet signature verification
CREATE TABLE IF NOT EXISTS `auth_nonces` (
  `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
  `nonce` VARCHAR(128) NOT NULL UNIQUE,
  `wallet_address` VARCHAR(42) NOT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `expires_at` TIMESTAMP NOT NULL,
  `used` BOOLEAN DEFAULT FALSE,
  `used_at` TIMESTAMP NULL,
  
  INDEX `idx_nonce` (`nonce`),
  INDEX `idx_wallet_address` (`wallet_address`),
  INDEX `idx_expires_at` (`expires_at`),
  INDEX `idx_used` (`used`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Table for storing blockchain configuration
CREATE TABLE IF NOT EXISTS `blockchain_config` (
  `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
  `contract_address` VARCHAR(42) NOT NULL,
  `contract_name` VARCHAR(128) NOT NULL,
  `rpc_url` VARCHAR(512) NOT NULL,
  `chain_id` BIGINT NOT NULL,
  `is_active` BOOLEAN DEFAULT TRUE,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  
  INDEX `idx_contract_address` (`contract_address`),
  INDEX `idx_chain_id` (`chain_id`),
  INDEX `idx_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Insert default blockchain configuration
INSERT INTO `blockchain_config` (`contract_address`, `contract_name`, `rpc_url`, `chain_id`) 
VALUES 
('0xContractAddress', 'LabReservationContract', 'https://rpc.blockchain.com', 1) 
ON DUPLICATE KEY UPDATE 
  `contract_name` = VALUES(`contract_name`),
  `rpc_url` = VALUES(`rpc_url`),
  `chain_id` = VALUES(`chain_id`),
  `updated_at` = CURRENT_TIMESTAMP;

CREATE INDEX `idx_auth_users_active` ON `auth_users` (`is_active`, `created_at`);
CREATE INDEX `idx_jwt_tokens_active` ON `jwt_tokens` (`revoked`, `expires_at`);
CREATE INDEX `idx_lab_reservations_active` ON `lab_reservations` (`status`, `start_time`, `end_time`);
CREATE INDEX `idx_auth_sessions_active` ON `auth_sessions` (`is_active`, `expires_at`);
CREATE INDEX `idx_auth_nonces_valid` ON `auth_nonces` (`used`, `expires_at`);
