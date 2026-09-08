package com.example.business.approval;

import com.example.business.common.ApiException;
import java.time.OffsetDateTime;
import java.util.UUID;
import java.util.Set;

public final class ApprovalModels {
    private ApprovalModels() {}
    public static String text(String value, int max) {
        if (value == null || value.isBlank() || value.length() > max)
            throw new ApiException(422, "INVALID_DRAFT", "초안 필드를 확인하세요.");
        return value.strip();
    }
    public record Draft(String incidentId, String title, String body, String team, String priority) {
        public Draft {
            incidentId = text(incidentId, 32); title = text(title, 200);
            body = text(body, 6000); team = text(team, 80); priority = text(priority, 2);
            if (!Set.of("P1", "P2", "P3").contains(priority))
                throw new ApiException(422, "INVALID_DRAFT", "등급을 확인하세요.");
        }
    }
    public record CreateApproval(UUID runId, Integer proposalVersion, Draft draft) {
        public CreateApproval {
            if (runId == null || proposalVersion == null || proposalVersion < 1 || draft == null)
                throw new ApiException(422, "INVALID_DRAFT", "실행 ID·초안 버전을 확인하세요.");
        }
    }
    public record Decision(String decision) {
        public Decision {
            if (!"approve".equals(decision) && !"reject".equals(decision))
                throw new ApiException(422, "INVALID_DECISION", "approve 또는 reject를 지정하세요.");
        }
    }
    public record CreateTicket(UUID approvalId, String draftHash) {
        public CreateTicket {
            if (approvalId == null || draftHash == null || !draftHash.matches("[a-f0-9]{64}"))
                throw new ApiException(422, "INVALID_DRAFT", "승인 ID·초안 해시를 확인하세요.");
        }
    }
    public record Approval(UUID approvalId, UUID runId, int proposalVersion, String ownerId,
                           Draft draft, String draftHash, String status, OffsetDateTime expiresAt, UUID ticketId) {}
    public record Ticket(UUID id, UUID approvalId, String incidentId, String title, String body,
                         String team, String priority, String status, OffsetDateTime createdAt) {}
    public record CreatedTicket(Ticket ticket, boolean created) {}
}
