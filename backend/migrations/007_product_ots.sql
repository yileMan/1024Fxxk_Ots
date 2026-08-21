CREATE TABLE product_ots (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    product_version_id BIGINT UNSIGNED NOT NULL,
    ots_component_id BIGINT UNSIGNED NOT NULL,
    created_by BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT pk_product_ots PRIMARY KEY (id),
    CONSTRAINT fk_product_ots_version FOREIGN KEY (product_version_id) REFERENCES product_version(id),
    CONSTRAINT fk_product_ots_component FOREIGN KEY (ots_component_id) REFERENCES ots_component(id),
    CONSTRAINT fk_product_ots_created_by FOREIGN KEY (created_by) REFERENCES app_user(id),
    CONSTRAINT uk_product_version_ots UNIQUE (product_version_id, ots_component_id),
    INDEX idx_product_ots_component (ots_component_id, product_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
