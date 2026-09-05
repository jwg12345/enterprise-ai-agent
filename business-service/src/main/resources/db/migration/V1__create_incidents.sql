CREATE TABLE incidents (
    id varchar(32) PRIMARY KEY,
    category varchar(20) NOT NULL CHECK (category IN ('NETWORK','SERVER','APPLICATION')),
    severity varchar(2) NOT NULL CHECK (severity IN ('P1','P2','P3')),
    status varchar(20) NOT NULL CHECK (status IN ('OPEN','IN_PROGRESS','RESOLVED')),
    occurred_at timestamptz NOT NULL,
    cause text NOT NULL,
    version bigint NOT NULL DEFAULT 1
);
CREATE INDEX incidents_filter_idx ON incidents (occurred_at, category, severity);
