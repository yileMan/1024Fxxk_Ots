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

CREATE TABLE audit_log (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NULL,
    action VARCHAR(16) NOT NULL,
    object_type VARCHAR(64) NOT NULL,
    object_id VARCHAR(100) NULL,
    detail_json JSON NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT pk_audit_log PRIMARY KEY (id),
    CONSTRAINT fk_audit_log_user FOREIGN KEY (user_id) REFERENCES app_user(id),
    CONSTRAINT ck_audit_log_action CHECK (action IN ('insert', 'update', 'delete', 'batch_upsert')),
    INDEX idx_audit_time (created_at),
    INDEX idx_audit_user_time (user_id, created_at),
    INDEX idx_audit_object (object_type, object_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
