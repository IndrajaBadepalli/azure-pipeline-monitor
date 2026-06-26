-- ============================================
-- Metadata Schema for Azure Pipeline Monitor
-- Database: pipeline-metadata
-- ============================================

-- Track every pipeline run
CREATE TABLE pipeline_runs (
    run_id           UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    pipeline_name    NVARCHAR(200)     NOT NULL,
    adf_run_id       NVARCHAR(200),
    started_at       DATETIMEOFFSET,
    ended_at         DATETIMEOFFSET,
    status           NVARCHAR(50),
    rows_processed   BIGINT,
    duration_sec     DECIMAL(10,2),
    triggered_by     NVARCHAR(100),
    environment      NVARCHAR(50) DEFAULT 'dev'
);

-- Data quality check results
CREATE TABLE quality_results (
    result_id        UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    run_id           UNIQUEIDENTIFIER REFERENCES pipeline_runs(run_id),
    table_name       NVARCHAR(200),
    check_name       NVARCHAR(100),
    status           NVARCHAR(50),
    observed_value   DECIMAL(18,4),
    expected_value   DECIMAL(18,4),
    details          NVARCHAR(MAX),
    checked_at       DATETIMEOFFSET DEFAULT GETUTCDATE()
);

-- Incidents raised when a check fails
CREATE TABLE incidents (
    incident_id      UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    run_id           UNIQUEIDENTIFIER REFERENCES pipeline_runs(run_id),
    severity         NVARCHAR(20),
    summary          NVARCHAR(500),
    rca_text         NVARCHAR(MAX),
    suggested_fix    NVARCHAR(MAX),
    context_bundle   NVARCHAR(MAX),
    created_at       DATETIMEOFFSET DEFAULT GETUTCDATE(),
    resolved_at      DATETIMEOFFSET,
    status           NVARCHAR(50) DEFAULT 'open'
);

-- Schema snapshots for drift detection
CREATE TABLE schema_snapshots (
    snapshot_id  UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    table_name   NVARCHAR(200),
    column_name  NVARCHAR(200),
    data_type    NVARCHAR(100),
    captured_at  DATETIMEOFFSET DEFAULT GETUTCDATE()
);

-- Data lineage events
CREATE TABLE lineage_events (
    event_id       UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    source_name    NVARCHAR(200),
    source_type    NVARCHAR(50),
    target_name    NVARCHAR(200),
    target_type    NVARCHAR(50),
    transformation NVARCHAR(100),
    run_id         NVARCHAR(200),
    row_count      BIGINT,
    extra          NVARCHAR(MAX),
    created_at     DATETIMEOFFSET DEFAULT GETUTCDATE()
);

-- Verify all tables created
SELECT TABLE_NAME 
FROM INFORMATION_SCHEMA.TABLES 
WHERE TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;