#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=business_password="$BUSINESS_DB_PASSWORD" --set=agent_password="$AGENT_DB_PASSWORD" <<'SQL'
REVOKE ALL ON DATABASE enterprise FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE ROLE business_app LOGIN PASSWORD :'business_password';
CREATE ROLE agent_app LOGIN PASSWORD :'agent_password';
GRANT CONNECT ON DATABASE enterprise TO business_app, agent_app;
CREATE SCHEMA business AUTHORIZATION business_app;
CREATE SCHEMA agent AUTHORIZATION agent_app;
ALTER ROLE business_app SET search_path TO business;
ALTER ROLE agent_app SET search_path TO agent;
SQL
