-- ============================================================================
-- BACKUP DE BASE DE DATOS MYSQL - PROYECTO BARRICA (SISTEMA POS / CRM DE BAR)
-- Motor: MySQL 8.0 (InnoDB, utf8mb4_unicode_ci)
-- ============================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------------------------------------------------------
-- 1. Estructura de tabla: users
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `users` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `full_name` VARCHAR(120) NOT NULL,
    `email` VARCHAR(254) NOT NULL,
    `password_hash` VARCHAR(100) NOT NULL,
    `role` VARCHAR(20) NOT NULL DEFAULT 'vendedor',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_users_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 2. Estructura de tabla: sessions
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `sessions` (
    `token_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `user_id` BIGINT UNSIGNED NOT NULL,
    `role` VARCHAR(20) NOT NULL DEFAULT 'vendedor',
    `expires_at` DATETIME NOT NULL,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`token_hash`),
    KEY `idx_sessions_user_id` (`user_id`),
    KEY `idx_sessions_expires_at` (`expires_at`),
    CONSTRAINT `fk_sessions_user`
        FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 3. Estructura de tabla: auth_attempts
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `auth_attempts` (
    `key_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `attempts` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    `window_started_at` DATETIME NOT NULL,
    `last_attempt_at` DATETIME NOT NULL,
    PRIMARY KEY (`key_hash`),
    KEY `idx_auth_attempts_last_attempt_at` (`last_attempt_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 4. Estructura de tabla: products
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `products` (
    `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `name` VARCHAR(120) NOT NULL,
    `category` VARCHAR(60) NOT NULL DEFAULT 'Licores',
    `price_cop` INT UNSIGNED NOT NULL,
    `stock` INT NOT NULL DEFAULT 0,
    `min_stock` INT NOT NULL DEFAULT 5,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 5. Estructura de tabla: bar_tables
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `bar_tables` (
    `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `table_number` INT UNSIGNED NOT NULL,
    `label` VARCHAR(60) NOT NULL,
    `capacity` SMALLINT UNSIGNED NOT NULL DEFAULT 4,
    `status` VARCHAR(20) NOT NULL DEFAULT 'libre',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_bar_tables_number` (`table_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 6. Estructura de tabla: table_orders
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `table_orders` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `table_id` INT UNSIGNED NOT NULL,
    `product_id` INT UNSIGNED NULL,
    `product_name` VARCHAR(120) NOT NULL,
    `quantity` INT UNSIGNED NOT NULL DEFAULT 1,
    `unit_price_cop` INT UNSIGNED NOT NULL,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_table_orders_table_id` (`table_id`),
    CONSTRAINT `fk_table_orders_table`
        FOREIGN KEY (`table_id`) REFERENCES `bar_tables` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_table_orders_product`
        FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 7. Estructura de tabla: sales
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `sales` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `table_label` VARCHAR(60) NOT NULL,
    `items_summary` VARCHAR(500) NOT NULL,
    `total_cop` INT UNSIGNED NOT NULL,
    `payment_method` VARCHAR(40) NOT NULL DEFAULT 'Efectivo',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_sales_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- Datos semilla operativos: bar_tables
-- ----------------------------------------------------------------------------
INSERT IGNORE INTO `bar_tables` (`id`, `table_number`, `label`, `capacity`, `status`) VALUES
(1, 1, 'Mesa 1 · Salón', 4, 'libre'),
(2, 2, 'Mesa 2 · Salón', 4, 'libre'),
(3, 3, 'Mesa 3 · Ventana', 2, 'libre'),
(4, 4, 'Mesa 4 · Terraza', 6, 'libre'),
(5, 5, 'Mesa 5 · Terraza', 4, 'libre'),
(6, 6, 'Mesa 6 · VIP', 8, 'libre'),
(7, 7, 'Barra 1 · Principal', 2, 'libre'),
(8, 8, 'Barra 2 · Principal', 2, 'libre');

-- ----------------------------------------------------------------------------
-- Datos semilla operativos: products
-- ----------------------------------------------------------------------------
INSERT IGNORE INTO `products` (`id`, `name`, `category`, `price_cop`, `stock`, `min_stock`) VALUES
(1, 'Negroni', 'Cócteles', 28000, 24, 5),
(2, 'Old Fashioned', 'Cócteles', 30000, 20, 5),
(3, 'Margarita Artesanal', 'Cócteles', 26000, 18, 5),
(4, 'Cerveza Club Colombia', 'Cervezas', 9000, 48, 12),
(5, 'Cerveza Artesanal IPA', 'Cervezas', 15000, 30, 8),
(6, 'Botella Ginebra Tanqueray', 'Licores', 165000, 3, 4),
(7, 'Botella Aguardiente Antioqueño', 'Licores', 85000, 10, 4),
(8, 'Tabla de Quesos y Madurados', 'Comida', 42000, 12, 3);

SET FOREIGN_KEY_CHECKS = 1;
