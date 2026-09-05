package com.example.business.incident;

import java.util.*;
import java.time.OffsetDateTime;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class IncidentRepository {
    private final NamedParameterJdbcTemplate jdbc;
    public IncidentRepository(NamedParameterJdbcTemplate jdbc) { this.jdbc = jdbc; }
    public record Page(List<Incident> items, int page, int size, long total) {}

    @Transactional(readOnly = true, isolation = org.springframework.transaction.annotation.Isolation.REPEATABLE_READ)
    public Page find(IncidentQuery q) {
        StringBuilder where = new StringBuilder(" WHERE occurred_at >= :from AND occurred_at < :to");
        Map<String,Object> params = new HashMap<>();
        params.put("from", q.from()); params.put("to", q.to());
        if (q.severity() != null) { where.append(" AND severity = :severity"); params.put("severity", q.severity()); }
        if (q.category() != null) { where.append(" AND category = :category"); params.put("category", q.category()); }
        if (q.status() != null) { where.append(" AND status = :status"); params.put("status", q.status()); }
        Long total = jdbc.queryForObject("SELECT count(*) FROM business.incidents" + where, params, Long.class);
        params.put("limit", q.size()); params.put("offset", (long) q.page() * q.size());
        var items = jdbc.query("SELECT * FROM business.incidents" + where
            + " ORDER BY occurred_at DESC, id ASC LIMIT :limit OFFSET :offset", params,
            (rs, row) -> new Incident(rs.getString("id"), rs.getString("category"), rs.getString("severity"),
                rs.getString("status"), rs.getObject("occurred_at", OffsetDateTime.class),
                rs.getString("cause"), rs.getLong("version")));
        return new Page(items, q.page(), q.size(), total == null ? 0 : total);
    }
}
