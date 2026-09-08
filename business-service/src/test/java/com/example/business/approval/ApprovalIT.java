package com.example.business.approval;

import static com.example.business.approval.ApprovalModels.*;
import static org.junit.jupiter.api.Assertions.*;
import com.example.business.common.ApiException;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(properties = "BUSINESS_SERVICE_TOKEN=integration-service-token-32-characters")
class ApprovalIT {
    @Container static PostgreSQLContainer<?> db = new PostgreSQLContainer<>("postgres:17.6");
    @DynamicPropertySource static void database(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", db::getJdbcUrl);
        registry.add("spring.datasource.username", db::getUsername);
        registry.add("spring.datasource.password", db::getPassword);
    }
    @Autowired ApprovalService service;
    @Autowired JdbcTemplate jdbc;
    private static final String OWNER = "demo-operator";
    @BeforeEach void seed() {
        jdbc.execute("TRUNCATE business.ticket_idempotency,business.tickets,business.approvals,business.audit_events,business.incidents CASCADE");
        jdbc.update("INSERT INTO business.incidents(id,category,severity,status,occurred_at,cause) VALUES('INC-TEST','NETWORK','P1','OPEN',now(),'synthetic')");
    }
    private Approval draft() {
        return service.create(new CreateApproval(UUID.randomUUID(), 1,
            new Draft("INC-TEST", "점검", "합성 본문", "Platform", "P1")), OWNER, "operator", "test");
    }
    private void approve(Approval a) { service.decide(a.approvalId(), new Decision("approve"), OWNER, "operator", "test"); }
    private CreatedTicket create(Approval a, String key) {
        return service.createTicket(new CreateTicket(a.approvalId(), a.draftHash()), key, OWNER, "operator", "test");
    }
    private void error(String code, org.junit.jupiter.api.function.Executable action) {
        assertEquals(code, assertThrows(ApiException.class, action).code);
    }
    @Test void approvalRequiredThenIdempotentCreationAndOwnership() {
        Approval a = draft();
        error("APPROVAL_REQUIRED", () -> create(a, "first"));
        error("FORBIDDEN", () -> service.decide(a.approvalId(), new Decision("approve"), "demo-viewer", "viewer", "test"));
        error("NOT_FOUND", () -> service.decide(a.approvalId(), new Decision("approve"), "other", "operator", "test"));
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM business.tickets", Integer.class));
        approve(a);
        var first = create(a, "first");
        assertTrue(first.created());
        assertEquals(first.ticket().id(), create(a, "first").ticket().id());
        assertEquals(first.ticket().id(), create(a, "another-key").ticket().id());
        error("NOT_FOUND", () -> service.getTicket(first.ticket().id(), "other"));
        assertEquals("EXECUTED", service.get(a.approvalId(), OWNER, "test").status());
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM business.tickets", Integer.class));
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM business.audit_events WHERE action='TICKET_CREATED'", Integer.class));
    }
    @Test void rejectionExpiryTamperingAndResolvedIncidentCannotCreate() {
        Approval rejected = draft();
        service.decide(rejected.approvalId(), new Decision("reject"), OWNER, "operator", "test");
        error("DECISION_CONFLICT", () -> approve(rejected));
        error("APPROVAL_REQUIRED", () -> create(rejected, "rejected"));
        Approval expired = draft();
        approve(expired);
        jdbc.update("UPDATE business.approvals SET expires_at=now()-interval '1 second' WHERE id=?", expired.approvalId());
        error("APPROVAL_EXPIRED", () -> create(expired, "expired"));
        assertEquals("EXPIRED", service.get(expired.approvalId(), OWNER, "test").status());
        Approval tampered = draft(); approve(tampered);
        error("DRAFT_MISMATCH", () -> service.createTicket(new CreateTicket(tampered.approvalId(), "0".repeat(64)),
                                                          "bad", OWNER, "operator", "test"));
        jdbc.update("UPDATE business.incidents SET status='RESOLVED' WHERE id='INC-TEST'");
        error("INCIDENT_RESOLVED", () -> create(tampered, "resolved"));
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM business.tickets", Integer.class));
    }
    @Test void sameRunCannotChangeDraftAndKeyCannotChangeRequest() {
        Approval a = draft();
        var input = new CreateApproval(a.runId(), 1, a.draft());
        assertEquals(a.approvalId(), service.create(input, OWNER, "operator", "test").approvalId());
        error("PROPOSAL_CONFLICT", () -> service.create(new CreateApproval(a.runId(), 1,
            new Draft("INC-TEST", "변조", "본문", "Platform", "P1")), OWNER, "operator", "test"));
        error("PROPOSAL_IMMUTABLE", () -> service.create(new CreateApproval(a.runId(), 2, a.draft()), OWNER, "operator", "test"));
        approve(a); create(a, "same-key");
        Approval b = draft(); approve(b);
        error("IDEMPOTENCY_CONFLICT", () -> create(b, "same-key"));
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM business.tickets", Integer.class));
    }
    @Test void simultaneousRequestsCreateOneTicket() throws Exception {
        Approval a = draft(); approve(a);
        var start = new CountDownLatch(1);
        try (var pool = Executors.newFixedThreadPool(6)) {
            List<Future<CreatedTicket>> pending = new ArrayList<>();
            for (int i=0; i<6; i++) {
                String key = "parallel-" + (i % 3);
                pending.add(pool.submit(() -> { start.await(); return create(a, key); }));
            }
            start.countDown();
            Set<UUID> ids = new HashSet<>(); int created = 0;
            for (var future : pending) {
                var result = future.get(20, TimeUnit.SECONDS);
                ids.add(result.ticket().id()); if (result.created()) created++;
            }
            assertEquals(1, ids.size()); assertEquals(1, created);
        }
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM business.tickets", Integer.class));
    }
    @Test void auditFailureRollsBackTicketAndApprovalTransition() {
        Approval a = draft(); approve(a);
        jdbc.execute("ALTER TABLE business.audit_events ADD CONSTRAINT reject_ticket_audit CHECK(action <> 'TICKET_CREATED')");
        try {
            assertThrows(org.springframework.dao.DataAccessException.class, () -> create(a, "rollback"));
            assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM business.tickets", Integer.class));
            assertEquals("APPROVED", service.get(a.approvalId(), OWNER, "test").status());
        } finally { jdbc.execute("ALTER TABLE business.audit_events DROP CONSTRAINT reject_ticket_audit"); }
    }
}
