-- Create the Airflow metadata database if it does not already exist.
-- The researchlineage database is created automatically by POSTGRES_DB in
-- the docker-compose environment; this script handles the additional one.
SELECT 'CREATE DATABASE airflow'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow')\gexec
