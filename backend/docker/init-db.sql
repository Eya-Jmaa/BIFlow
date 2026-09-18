-- Analytical role used for generated read-only queries.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'biflow_analytics') THEN
        CREATE ROLE biflow_analytics LOGIN PASSWORD 'change-me-in-production';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE biflow TO biflow_analytics;
