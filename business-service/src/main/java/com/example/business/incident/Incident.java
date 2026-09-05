package com.example.business.incident;

import java.time.OffsetDateTime;

public record Incident(String id, String category, String severity, String status,
                       OffsetDateTime occurredAt, String cause, long version) {}
