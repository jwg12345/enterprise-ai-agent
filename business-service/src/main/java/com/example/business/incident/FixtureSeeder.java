package com.example.business.incident;

import java.nio.file.*;
import java.time.OffsetDateTime;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class FixtureSeeder {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    public FixtureSeeder(JdbcTemplate jdbc, ObjectMapper mapper) { this.jdbc = jdbc; this.mapper = mapper; }
    @Transactional
    public int seed(Path path) throws java.io.IOException {
        var rows = mapper.readTree(Files.readString(path));
        int inserted = 0;
        for (var row : rows) {
            inserted += jdbc.update("""
                INSERT INTO business.incidents (id,category,severity,status,occurred_at,cause,version)
                VALUES (?,?,?,?,?,?,?) ON CONFLICT (id) DO NOTHING
                """, row.required("id").asText(), row.required("category").asText(),
                row.required("severity").asText(), row.required("status").asText(),
                OffsetDateTime.parse(row.required("occurred_at").asText()),
                row.required("cause").asText(), row.required("version").asLong());
        }
        return inserted;
    }
}
