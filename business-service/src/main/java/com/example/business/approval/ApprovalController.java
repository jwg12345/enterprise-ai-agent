package com.example.business.approval;

import static com.example.business.approval.ApprovalModels.*;
import jakarta.servlet.http.HttpServletRequest;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1")
public class ApprovalController {
    private final ApprovalService service;
    public ApprovalController(ApprovalService service) { this.service = service; }
    private String owner(HttpServletRequest r) { return r.getHeader("X-User-ID"); }
    private String role(HttpServletRequest r) { return r.getHeader("X-User-Role"); }
    private String trace(HttpServletRequest r) { return (String) r.getAttribute("request_id"); }

    @PostMapping("/approvals")
    public ResponseEntity<Approval> create(@RequestBody CreateApproval input, HttpServletRequest r) {
        ApprovalService.operator(role(r));
        return ResponseEntity.status(201).body(service.create(input, owner(r), role(r), trace(r)));
    }
    @GetMapping("/approvals/{id}")
    public Approval get(@PathVariable UUID id, HttpServletRequest r) {
        return service.get(id, owner(r), trace(r));
    }
    @PostMapping("/approvals/{id}/decision")
    public Approval decide(@PathVariable UUID id, @RequestBody Decision input, HttpServletRequest r) {
        ApprovalService.operator(role(r));
        return service.decide(id, input, owner(r), role(r), trace(r));
    }
    @PostMapping("/tickets")
    public ResponseEntity<Ticket> createTicket(@RequestBody CreateTicket input,
            @RequestHeader(value="Idempotency-Key", required=false) String key, HttpServletRequest r) {
        ApprovalService.operator(role(r));
        CreatedTicket result = service.createTicket(input, key, owner(r), role(r), trace(r));
        return ResponseEntity.status(result.created() ? 201 : 200).body(result.ticket());
    }
    @GetMapping("/tickets/{id}")
    public Ticket ticket(@PathVariable UUID id, HttpServletRequest r) { return service.getTicket(id, owner(r)); }
}
