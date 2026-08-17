CREATE TABLE app_user (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    login_name VARCHAR(64) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    roles_json JSON NOT NULL,
    status VARCHAR(32) NOT NULL,
    last_login_at DATETIME(3) NULL,
    row_version INT UNSIGNED NOT NULL DEFAULT 1,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT pk_app_user PRIMARY KEY (id),
    CONSTRAINT uk_app_user_login UNIQUE (login_name),
    CONSTRAINT ck_app_user_status CHECK (status IN ('active', 'disabled')),
    CONSTRAINT ck_app_user_roles CHECK (JSON_TYPE(roles_json) = 'ARRAY'),
    INDEX idx_app_user_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
