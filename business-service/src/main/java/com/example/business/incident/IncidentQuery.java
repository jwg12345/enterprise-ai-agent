package com.example.business.incident;

import java.time.*;
import java.util.*;
import org.springframework.util.MultiValueMap;
import com.example.business.common.ApiException;

public record IncidentQuery(OffsetDateTime from, OffsetDateTime to, String severity,
                            String category, String status, int page, int size) {
    private static final Set<String> KEYS = Set.of("from","to","severity","category","status","page","size");
    public static IncidentQuery parse(MultiValueMap<String,String> params) {
        try {
            if (!KEYS.containsAll(params.keySet()) || params.values().stream().anyMatch(v -> v.size() != 1))
                throw new IllegalArgumentException();
            var from = OffsetDateTime.parse(Objects.requireNonNull(params.getFirst("from")));
            var to = OffsetDateTime.parse(Objects.requireNonNull(params.getFirst("to")));
            var duration = Duration.between(from, to);
            int page = Integer.parseInt(params.getFirst("page") == null ? "0" : params.getFirst("page"));
            int size = Integer.parseInt(params.getFirst("size") == null ? "20" : params.getFirst("size"));
            if (duration.isNegative() || duration.isZero() || duration.compareTo(Duration.ofDays(366)) > 0
                    || page < 0 || page > 100000 || size < 1 || size > 50) throw new IllegalArgumentException();
            return new IncidentQuery(from, to,
                choice(params.getFirst("severity"), Set.of("P1","P2","P3")),
                choice(params.getFirst("category"), Set.of("NETWORK","SERVER","APPLICATION")),
                choice(params.getFirst("status"), Set.of("OPEN","IN_PROGRESS","RESOLVED")), page, size);
        } catch (RuntimeException e) {
            throw new ApiException(422, "INVALID_QUERY", "기간·등급·분류·페이지 조건을 확인하세요.");
        }
    }
    private static String choice(String value, Set<String> allowed) {
        if (value != null && !allowed.contains(value)) throw new IllegalArgumentException();
        return value;
    }
}
