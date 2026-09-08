CREATE TABLE approvals (
    id uuid PRIMARY KEY,
    run_id uuid NOT NULL,
    proposal_version integer NOT NULL CHECK (proposal_version > 0),
    owner_id varchar(64) NOT NULL,
    incident_id varchar(32) NOT NULL REFERENCES incidents(id),
    draft_json jsonb NOT NULL,
    draft_hash char(64) NOT NULL,
    status varchar(16) NOT NULL CHECK (status IN ('PENDING','APPROVED','REJECTED','EXPIRED','EXECUTED')),
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    decided_by varchar(64),
    decided_at timestamptz,
    UNIQUE (run_id, proposal_version)
);
CREATE TABLE tickets (
    id uuid PRIMARY KEY,
    approval_id uuid NOT NULL UNIQUE REFERENCES approvals(id),
    incident_id varchar(32) NOT NULL REFERENCES incidents(id),
    owner_id varchar(64) NOT NULL,
    title varchar(200) NOT NULL,
    body text NOT NULL,
    team varchar(80) NOT NULL,
    priority varchar(2) NOT NULL CHECK (priority IN ('P1','P2','P3')),
    status varchar(16) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','CLOSED')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE ticket_idempotency (
    owner_id varchar(64) NOT NULL,
    idempotency_key varchar(128) NOT NULL,
    request_hash char(64) NOT NULL,
    ticket_id uuid NOT NULL REFERENCES tickets(id),
    PRIMARY KEY (owner_id, idempotency_key)
);
CREATE TABLE audit_events (
    id uuid PRIMARY KEY,
    actor_id varchar(64) NOT NULL,
    action varchar(32) NOT NULL,
    resource_id uuid NOT NULL,
    request_id varchar(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX approvals_owner_idx ON approvals(owner_id, created_at);
