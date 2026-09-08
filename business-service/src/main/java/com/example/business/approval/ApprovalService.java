package com.example.business.approval;

import static com.example.business.approval.ApprovalModels.*;
import com.example.business.common.ApiException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.OffsetDateTime;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ApprovalService {
    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final int ttl;
    public ApprovalService(NamedParameterJdbcTemplate jdbc, ObjectMapper mapper,
                           @Value("${APPROVAL_TTL_SECONDS:900}") int ttl) {
        if (ttl < 1 || ttl > 86400) throw new IllegalArgumentException("Invalid approval TTL");
        this.jdbc = jdbc; this.mapper = mapper; this.ttl = ttl;
    }
    public static void operator(String role) {
        if (!"operator".equals(role)) throw new ApiException(403, "FORBIDDEN", "운영자 권한이 필요합니다.");
    }
    private ApiException conflict(String code) { return new ApiException(409, code, "승인 상태와 초안을 확인하세요."); }
    private ApiException missing() { return new ApiException(404, "NOT_FOUND", "항목을 찾을 수 없습니다."); }
    private void lock(String key) {
        jdbc.query("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))", Map.of("key", key),
                   (rs, n) -> 0);
    }
    private void audit(String actor, String action, UUID resource, String requestId) {
        jdbc.update("INSERT INTO business.audit_events(id,actor_id,action,resource_id,request_id) "
                    + "VALUES(:id,:actor,:action,:resource,:request)",
                    Map.of("id", UUID.randomUUID(), "actor", actor, "action", action,
                           "resource", resource, "request", requestId));
    }
    static String hash(String text) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                           .digest(text.getBytes(StandardCharsets.UTF_8))); }
        catch (java.security.NoSuchAlgorithmException ex) { throw new IllegalStateException(ex); }
    }
    String canonical(Draft draft) {
        try { return mapper.writeValueAsString(new TreeMap<>(Map.of("incident_id", draft.incidentId(),
            "title", draft.title(), "body", draft.body(), "team", draft.team(), "priority", draft.priority()))); }
        catch (com.fasterxml.jackson.core.JsonProcessingException ex) { throw new IllegalStateException(ex); }
    }
    private Draft parse(String json) {
        try {
            var n = mapper.readTree(json);
            return new Draft(n.get("incident_id").asText(), n.get("title").asText(), n.get("body").asText(),
                             n.get("team").asText(), n.get("priority").asText());
        } catch (com.fasterxml.jackson.core.JsonProcessingException ex) { throw new IllegalStateException(ex); }
    }
    private void unresolved(String id) {
        var statuses = jdbc.query("SELECT status FROM business.incidents WHERE id=:id FOR UPDATE", Map.of("id", id),
                                  (rs, n) -> rs.getString(1));
        if (statuses.isEmpty()) throw missing();
        if ("RESOLVED".equals(statuses.getFirst())) throw conflict("INCIDENT_RESOLVED");
    }
    private Approval approval(UUID id, String owner) {
        var rows = jdbc.query("SELECT a.* FROM business.approvals a "
            + "WHERE a.id=:id AND a.owner_id=:owner FOR UPDATE OF a",
            Map.of("id", id, "owner", owner), (rs, n) -> new Approval(rs.getObject("id", UUID.class),
                rs.getObject("run_id", UUID.class), rs.getInt("proposal_version"), rs.getString("owner_id"),
                parse(rs.getString("draft_json")), rs.getString("draft_hash"), rs.getString("status"),
                rs.getObject("expires_at", OffsetDateTime.class), null));
        if (rows.isEmpty()) throw missing();
        // 잠금 대기 전에 만들어진 JOIN 스냅샷으로 기존 티켓을 놓치지 않도록 별도로 조회합니다.
        var tickets = jdbc.query("SELECT id FROM business.tickets WHERE approval_id=:id", Map.of("id", id),
                                (rs, n) -> rs.getObject("id", UUID.class));
        Approval a = rows.getFirst();
        return new Approval(a.approvalId(), a.runId(), a.proposalVersion(), a.ownerId(), a.draft(),
                            a.draftHash(), a.status(), a.expiresAt(), tickets.isEmpty() ? null : tickets.getFirst());
    }
    private boolean expire(Approval a, String requestId) {
        if (!Set.of("PENDING", "APPROVED").contains(a.status())) return "EXPIRED".equals(a.status());
        int changed = jdbc.update("UPDATE business.approvals SET status='EXPIRED' "
            + "WHERE id=:id AND expires_at <= clock_timestamp()", Map.of("id", a.approvalId()));
        if (changed > 0) audit(a.ownerId(), "APPROVAL_EXPIRED", a.approvalId(), requestId);
        return changed > 0;
    }
    @Transactional
    public Approval create(CreateApproval input, String owner, String role, String requestId) {
        operator(role);
        lock("approval:" + input.runId());
        String json = canonical(input.draft()), digest = hash(json);
        var previous = jdbc.query("SELECT id,owner_id FROM business.approvals WHERE run_id=:run",
            Map.of("run", input.runId()),
            (rs, n) -> Map.entry(rs.getObject("id", UUID.class), rs.getString("owner_id")));
        if (!previous.isEmpty()) {
            if (!owner.equals(previous.getFirst().getValue())) throw missing();
            Approval a = approval(previous.getFirst().getKey(), owner);
            if (a.proposalVersion() != input.proposalVersion()) throw conflict("PROPOSAL_IMMUTABLE");
            if (!a.draftHash().equals(digest)) throw conflict("PROPOSAL_CONFLICT");
            expire(a, requestId);
            return approval(a.approvalId(), owner);
        }
        unresolved(input.draft().incidentId());
        UUID id = UUID.randomUUID();
        jdbc.update("INSERT INTO business.approvals(id,run_id,proposal_version,owner_id,incident_id,draft_json,"
            + "draft_hash,status,expires_at) VALUES(:id,:run,:version,:owner,:incident,CAST(:json AS jsonb),"
            + ":hash,'PENDING',clock_timestamp()+(:ttl * interval '1 second'))", Map.of("id", id,
            "run", input.runId(), "version", input.proposalVersion(), "owner", owner,
            "incident", input.draft().incidentId(), "json", json, "hash", digest, "ttl", ttl));
        audit(owner, "APPROVAL_CREATED", id, requestId);
        return approval(id, owner);
    }
    @Transactional
    public Approval get(UUID id, String owner, String requestId) {
        Approval a = approval(id, owner);
        expire(a, requestId);
        return approval(id, owner);
    }
    @Transactional(noRollbackFor = ApiException.class)
    public Approval decide(UUID id, Decision input, String owner, String role, String requestId) {
        operator(role);
        Approval a = approval(id, owner);
        if (expire(a, requestId)) throw conflict("APPROVAL_EXPIRED");
        String target = "approve".equals(input.decision()) ? "APPROVED" : "REJECTED";
        if (a.status().equals(target) || (a.status().equals("EXECUTED") && target.equals("APPROVED"))) return a;
        if (!a.status().equals("PENDING")) throw conflict("DECISION_CONFLICT");
        jdbc.update("UPDATE business.approvals SET status=:status,decided_by=:owner,decided_at=clock_timestamp() WHERE id=:id",
                    Map.of("status", target, "owner", owner, "id", id));
        audit(owner, "APPROVAL_" + target, id, requestId);
        return approval(id, owner);
    }
    private Ticket ticket(UUID id, String owner) {
        var rows = jdbc.query("SELECT * FROM business.tickets WHERE id=:id AND owner_id=:owner", Map.of("id", id, "owner", owner),
            (rs, n) -> new Ticket(rs.getObject("id", UUID.class), rs.getObject("approval_id", UUID.class),
                rs.getString("incident_id"), rs.getString("title"), rs.getString("body"), rs.getString("team"),
                rs.getString("priority"), rs.getString("status"), rs.getObject("created_at", OffsetDateTime.class)));
        if (rows.isEmpty()) throw missing();
        return rows.getFirst();
    }
    @Transactional(readOnly = true)
    public Ticket getTicket(UUID id, String owner) { return ticket(id, owner); }

    @Transactional(noRollbackFor = ApiException.class)
    public CreatedTicket createTicket(CreateTicket input, String key, String owner, String role, String requestId) {
        operator(role);
        if (key == null || !key.matches("[A-Za-z0-9._:-]{1,128}"))
            throw new ApiException(422, "INVALID_IDEMPOTENCY_KEY", "멱등 키를 확인하세요.");
        lock("ticket-key:" + owner + ":" + key);
        String digest = hash(input.approvalId() + ":" + input.draftHash());
        var cached = jdbc.query("SELECT request_hash,ticket_id FROM business.ticket_idempotency "
            + "WHERE owner_id=:owner AND idempotency_key=:key", Map.of("owner", owner, "key", key),
            (rs, n) -> Map.entry(rs.getString(1), rs.getObject(2, UUID.class)));
        if (!cached.isEmpty()) {
            if (!cached.getFirst().getKey().equals(digest)) throw conflict("IDEMPOTENCY_CONFLICT");
            return new CreatedTicket(ticket(cached.getFirst().getValue(), owner), false);
        }
        Approval a = approval(input.approvalId(), owner);
        if (!a.draftHash().equals(input.draftHash())) throw conflict("DRAFT_MISMATCH");
        boolean created = false;
        UUID ticketId = a.ticketId();
        if (ticketId == null) {
            if (expire(a, requestId)) throw conflict("APPROVAL_EXPIRED");
            if (!a.status().equals("APPROVED")) throw conflict("APPROVAL_REQUIRED");
            unresolved(a.draft().incidentId());
            if (expire(a, requestId)) throw conflict("APPROVAL_EXPIRED");
            ticketId = UUID.randomUUID();
            Draft d = a.draft();
            jdbc.update("INSERT INTO business.tickets(id,approval_id,incident_id,owner_id,title,body,team,priority) "
                + "VALUES(:id,:approval,:incident,:owner,:title,:body,:team,:priority)", Map.of("id", ticketId,
                    "approval", a.approvalId(), "incident", d.incidentId(), "owner", owner, "title", d.title(),
                    "body", d.body(), "team", d.team(), "priority", d.priority()));
            jdbc.update("UPDATE business.approvals SET status='EXECUTED' WHERE id=:id", Map.of("id", a.approvalId()));
            audit(owner, "TICKET_CREATED", ticketId, requestId);
            created = true;
        }
        jdbc.update("INSERT INTO business.ticket_idempotency(owner_id,idempotency_key,request_hash,ticket_id) "
            + "VALUES(:owner,:key,:hash,:ticket)", Map.of("owner", owner, "key", key, "hash", digest, "ticket", ticketId));
        return new CreatedTicket(ticket(ticketId, owner), created);
    }
}
