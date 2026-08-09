-- =========================================================================
-- setup_mysql_chatbot.sql
-- Setup the MySQL database used by the chatbot.
-- Since the `chatbot` and `glb-3d` databases were merged, everything lives in
-- `glb-3d` (the database shared with the GLB-AR website).
-- Creates the `products` table (same schema as the GLB-AR Laravel app),
-- seeds it with the sample products, and creates the `product_knowledge` table.
--
-- Assumes MySQL is running locally and user `root` has no password.
--
-- Run:
--   mysql -u root -p glb-3d < setup_mysql_chatbot.sql
-- =========================================================================

USE glb-3d;

CREATE TABLE IF NOT EXISTS products (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    product_id VARCHAR(255) NOT NULL UNIQUE,
    product_name VARCHAR(255) NOT NULL,
    description TEXT NULL,
    model_url VARCHAR(255) NOT NULL,
    poster_url VARCHAR(255) NULL,
    qr_code_url VARCHAR(255) NULL,
    category VARCHAR(255) NULL,
    metadata JSON NULL,
    view_count INT NOT NULL DEFAULT 0,
    ar_activation_count INT NOT NULL DEFAULT 0,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO products
    (product_id, product_name, description, model_url, poster_url, category, metadata, view_count, ar_activation_count, is_active, created_at, updated_at)
VALUES
    ('PROD-001', 'Modern Office Chair', 'Ergonomic office chair with adjustable height, lumbar support, and breathable mesh back. Perfect for long working hours with maximum comfort and style.',
     'https://modelviewer.dev/shared-assets/models/Astronaut.glb', NULL, 'Furniture',
     JSON_OBJECT('material', 'Premium Mesh & Aluminum', 'weight', '15 kg', 'dimensions', '65 x 65 x 120 cm', 'color', 'Charcoal Black'),
     0, 0, 1, NOW(), NOW()),
    ('PROD-002', 'Smart Home Speaker', 'Premium wireless speaker with 360° sound, voice assistant integration, and smart home control capabilities. Experience crystal-clear audio in any room.',
     'https://modelviewer.dev/shared-assets/models/RobotExpressive.glb', NULL, 'Electronics',
     JSON_OBJECT('connectivity', 'WiFi, Bluetooth 5.0', 'battery', '12 hours playback', 'weight', '1.2 kg', 'voice_assistant', 'Alexa, Google Assistant'),
     0, 0, 1, NOW(), NOW()),
    ('PROD-003', 'Luxury Watch Collection', 'Handcrafted Swiss timepiece featuring automatic movement, sapphire crystal glass, and genuine leather strap. A statement of elegance and precision.',
     'https://modelviewer.dev/shared-assets/models/MaterialsVariantsShoe.glb', NULL, 'Accessories',
     JSON_OBJECT('movement', 'Swiss Automatic', 'water_resistance', '50 meters', 'case_diameter', '42 mm', 'warranty', '5 years'),
     0, 0, 1, NOW(), NOW()),
    ('PROD-004', 'Electric Motorcycle', 'High-performance electric motorcycle with instant torque, 200km range, and cutting-edge design. The future of urban mobility is here.',
     'https://modelviewer.dev/shared-assets/models/NeilArmstrong.glb', NULL, 'Vehicles',
     JSON_OBJECT('range', '200 km', 'top_speed', '180 km/h', 'charging_time', '2 hours (fast charge)', 'motor_power', '75 kW'),
     0, 0, 1, NOW(), NOW()),
    ('PROD-005', 'AR Headset Pro', 'Next-generation augmented reality headset with 4K displays, spatial audio, and hand tracking. Transform how you work, play, and create.',
     'https://modelviewer.dev/shared-assets/models/Astronaut.glb', NULL, 'Technology',
     JSON_OBJECT('display', 'Dual 4K OLED', 'field_of_view', '110 degrees', 'tracking', '6DoF + Hand Tracking', 'battery', '4 hours'),
     0, 0, 1, NOW(), NOW());

-- -------------------------------------------------------------------------
-- Product knowledge base (managed from the GLB-AR admin panel)
--   * product_id → link to products.product_id (NULL = free-form / general)
--   * title      → short title of the knowledge entry
--   * content    → the knowledge text the chatbot uses
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS product_knowledge (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    product_id VARCHAR(255) NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL,
    INDEX idx_product_id (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;