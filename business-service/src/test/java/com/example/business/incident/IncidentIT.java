package com.example.business.incident;

import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.util.LinkedMultiValueMap;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@SpringBootTest(properties = "BUSINESS_SERVICE_TOKEN=integration-service-token-32-characters")
class IncidentIT {
    @Container static PostgreSQLContainer<?> db = new PostgreSQLContainer<>("postgres:17.6");
    @DynamicPropertySource static void database(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", db::getJdbcUrl);
        registry.add("spring.datasource.username", db::getUsername);
        registry.add("spring.datasource.password", db::getPassword);
    }
    @Autowired FixtureSeeder seeder;
    @Autowired IncidentRepository repository;

    @Test void migrationSeedRangeAndPaginationUsePostgresql() throws Exception {
        assertEquals(4, seeder.seed(Path.of("../data/fixtures/incidents.json")));
        assertEquals(0, seeder.seed(Path.of("../data/fixtures/incidents.json")));
        var params = new LinkedMultiValueMap<String,String>();
        params.add("from","2026-08-01T00:00:00+09:00");
        params.add("to","2026-09-01T00:00:00+09:00");
        params.add("severity","P1"); params.add("category","NETWORK");
        var page = repository.find(IncidentQuery.parse(params));
        assertEquals(2, page.total());
        assertEquals(List.of("INC-015","INC-014"), page.items().stream().map(Incident::id).toList());
        params.set("size","1"); params.set("page","1");
        assertEquals("INC-014", repository.find(IncidentQuery.parse(params)).items().getFirst().id());
        params.set("page","0"); params.set("status","OPEN");
        assertEquals(1, repository.find(IncidentQuery.parse(params)).total());
        params.set("from","2026-08-14T09:00:00+09:00");
        params.set("to","2026-08-14T09:00:01+09:00");
        assertEquals(1, repository.find(IncidentQuery.parse(params)).total());
        params.set("from","2026-08-14T08:59:59+09:00");
        params.set("to","2026-08-14T09:00:00+09:00");
        assertEquals(0, repository.find(IncidentQuery.parse(params)).total());
    }
}
