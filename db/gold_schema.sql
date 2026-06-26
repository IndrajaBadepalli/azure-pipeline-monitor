-- ============================================
-- Gold Schema for Azure Pipeline Monitor
-- Database: pipeline-gold
-- ============================================

CREATE TABLE fct_orders (
    order_id            BIGINT,
    customer_id         BIGINT,
    full_name           NVARCHAR(200),
    country             NVARCHAR(100),
    city                NVARCHAR(100),
    customer_segment    NVARCHAR(50),
    acquisition_channel NVARCHAR(50),
    order_timestamp     DATETIME2,
    order_date          DATE,
    order_hour          INT,
    status              NVARCHAR(50),
    amount              DECIMAL(18,2),
    currency            NVARCHAR(10),
    source_channel      NVARCHAR(50),
    product_id          BIGINT,
    product_category    NVARCHAR(100),
    ingested_at         DATETIME2
);

CREATE TABLE dim_customers (
    customer_id             BIGINT,
    full_name               NVARCHAR(200),
    email                   NVARCHAR(200),
    country                 NVARCHAR(100),
    city                    NVARCHAR(100),
    segment                 NVARCHAR(50),
    acquisition_channel     NVARCHAR(50),
    signup_date             DATE,
    total_orders            INT,
    total_spend             DECIMAL(18,2),
    avg_order_value         DECIMAL(18,2),
    last_order_date         DATE,
    days_since_last_order   INT,
    is_email_verified       BIT,
    preferred_currency      NVARCHAR(10),
    customer_age_days       INT
);

CREATE TABLE mart_segment_revenue (
    order_date              DATE,
    customer_segment        NVARCHAR(50),
    country                 NVARCHAR(100),
    total_orders            BIGINT,
    total_revenue           DECIMAL(18,2),
    avg_order_value         DECIMAL(18,2),
    unique_customers        BIGINT,
    revenue_per_customer    DECIMAL(18,2)
);

CREATE TABLE mart_customer_ltv (
    customer_id             BIGINT,
    full_name               NVARCHAR(200),
    segment                 NVARCHAR(50),
    country                 NVARCHAR(100),
    acquisition_channel     NVARCHAR(50),
    signup_date             DATE,
    last_order_date         DATE,
    first_order_date        DATE,
    recency_days            INT,
    order_count             BIGINT,
    total_revenue           DECIMAL(18,2),
    avg_order_value         DECIMAL(18,2),
    r_score                 INT,
    f_score                 INT,
    m_score                 INT,
    ltv_score               DECIMAL(5,2),
    ltv_tier                NVARCHAR(50)
);

CREATE TABLE mart_customer_activity (
    customer_id                 BIGINT,
    full_name                   NVARCHAR(200),
    segment                     NVARCHAR(50),
    country                     NVARCHAR(100),
    days_since_last_order       INT,
    orders_last_90d             BIGINT,
    revenue_last_90d            DECIMAL(18,2),
    avg_order_value_last_90d    DECIMAL(18,2),
    total_events_last_90d       BIGINT,
    logins_last_90d             BIGINT,
    support_tickets_last_90d    BIGINT,
    returns_last_90d            BIGINT,
    activity_tier               NVARCHAR(50)
);

-- Verify all tables created
SELECT TABLE_NAME 
FROM INFORMATION_SCHEMA.TABLES 
WHERE TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;