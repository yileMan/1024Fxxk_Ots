CREATE TABLE user_product_scope (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    scope_type VARCHAR(16) NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    product_version_id BIGINT UNSIGNED NULL,
    scope_key VARCHAR(64) NOT NULL,
    created_by BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT pk_user_product_scope PRIMARY KEY (id),
    CONSTRAINT fk_user_product_scope_user FOREIGN KEY (user_id) REFERENCES app_user(id),
    CONSTRAINT fk_user_product_scope_product FOREIGN KEY (product_id) REFERENCES product(id),
    CONSTRAINT fk_user_product_scope_version FOREIGN KEY (product_version_id) REFERENCES product_version(id),
    CONSTRAINT fk_user_product_scope_created_by FOREIGN KEY (created_by) REFERENCES app_user(id),
    CONSTRAINT ck_user_product_scope_type CHECK (scope_type IN ('product', 'version')),
    CONSTRAINT ck_user_product_scope_target CHECK (
        (scope_type = 'product' AND product_version_id IS NULL)
        OR (scope_type = 'version' AND product_version_id IS NOT NULL)
    ),
    CONSTRAINT uk_user_product_scope UNIQUE (user_id, scope_key),
    INDEX idx_scope_product (product_id, user_id),
    INDEX idx_scope_version (product_version_id, user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
