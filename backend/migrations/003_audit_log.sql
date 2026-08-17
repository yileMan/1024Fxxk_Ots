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
