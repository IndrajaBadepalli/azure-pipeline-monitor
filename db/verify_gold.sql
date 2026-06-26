-- Verify Gold tables in pipeline-gold database
-- Run this against pipeline-gold database

SELECT 'fct_orders' as table_name, COUNT(*) as row_count FROM fct_orders
UNION ALL
SELECT 'dim_customers', COUNT(*) FROM dim_customers
UNION ALL
SELECT 'mart_segment_revenue', COUNT(*) FROM mart_segment_revenue
UNION ALL
SELECT 'mart_customer_ltv', COUNT(*) FROM mart_customer_ltv
UNION ALL
SELECT 'mart_customer_activity', COUNT(*) FROM mart_customer_activity
ORDER BY table_name;