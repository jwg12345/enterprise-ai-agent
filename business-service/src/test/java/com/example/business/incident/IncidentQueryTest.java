package com.example.business.incident;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.util.LinkedMultiValueMap;
import static org.junit.jupiter.api.Assertions.*;
import com.example.business.common.ApiException;

class IncidentQueryTest {
    private LinkedMultiValueMap<String,String> valid() {
        var p = new LinkedMultiValueMap<String,String>();
        p.add("from", "2026-08-01T00:00:00+09:00");
        p.add("to", "2026-09-01T00:00:00+09:00");
        return p;
    }
    @Test void acceptsValidRange() {
        var q = IncidentQuery.parse(valid());
        assertEquals(20, q.size());
        assertEquals(0, q.page());
        assertEquals(9 * 3600, q.from().getOffset().getTotalSeconds());
    }
    @ParameterizedTest
    @CsvSource({"size,51", "size,0", "page,-1", "page,100001", "severity,P0",
                "category,SQL", "status,DROP", "from,2026-09-02T00:00:00Z",
                "from,2026-08-01T00:00:00", "to,2028-01-01T00:00:00Z"})
    void rejectsInvalidFilters(String key, String value) {
        var p = valid(); p.set(key, value);
        assertEquals(422, assertThrows(ApiException.class, () -> IncidentQuery.parse(p)).status);
    }
    @Test void rejectsDuplicateAndUnknownFilters() {
        var p = valid(); p.add("size", "2"); p.add("size", "3");
        assertThrows(ApiException.class, () -> IncidentQuery.parse(p));
        var unknown = valid(); unknown.add("sql", "SELECT");
        assertThrows(ApiException.class, () -> IncidentQuery.parse(unknown));
    }
}
