-- Clear the warranty dashboard cache
DELETE FROM warranty_dashboard_cache;

-- Reset the sequence for cache records
-- This will ensure new cache records start from 1
ALTER SEQUENCE warranty_dashboard_cache_id_seq RESTART WITH 1;