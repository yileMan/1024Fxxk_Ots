CREATE TABLE ots_component (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    ots_name VARCHAR(200) NOT NULL,
    ots_version VARCHAR(200) NOT NULL,
    official_website VARCHAR(1000) NOT NULL,
    is_eol TINYINT(1) NOT NULL,
    row_version INT UNSIGNED NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT pk_ots_component PRIMARY KEY (id),
    CONSTRAINT uk_ots_name_version UNIQUE (ots_name, ots_version),
    INDEX idx_ots_name (ots_name),
    INDEX idx_ots_eol (is_eol)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
