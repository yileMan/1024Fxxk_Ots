ALTER TABLE product_ots
    ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'active' AFTER created_by,
    ADD COLUMN row_version INT NOT NULL DEFAULT 1 AFTER status,
    ADD CONSTRAINT ck_product_ots_status CHECK (status IN ('active', 'disabled')),
    ADD INDEX idx_product_ots_status (status, product_version_id, ots_component_id);

ALTER TABLE product_assessment
    ADD COLUMN assessment_basis_sha256 CHAR(64) NULL AFTER based_on_source_modified_at,
    ADD COLUMN assessment_basis_json JSON NULL AFTER assessment_basis_sha256,
    ADD COLUMN reassess_changes_json JSON NULL AFTER assessment_basis_json;
