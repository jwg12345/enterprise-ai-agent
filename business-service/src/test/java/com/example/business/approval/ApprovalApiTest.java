package com.example.business.approval;

import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.junit.jupiter.api.Assertions.*;
import com.example.business.common.Errors;
import com.example.business.common.ApiException;
import com.example.business.security.ServiceAuthFilter;
import com.fasterxml.jackson.databind.*;
import org.junit.jupiter.api.*;
import org.springframework.http.MediaType;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import java.util.UUID;

class ApprovalApiTest {
    private MockMvc api;
    private ApprovalService service;
    private final String token = "s".repeat(32);
    @BeforeEach void setup() {
        service = mock(ApprovalService.class);
        var mapper = new ObjectMapper().findAndRegisterModules().setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
        api = MockMvcBuilders.standaloneSetup(new ApprovalController(service)).setControllerAdvice(new Errors())
            .setMessageConverters(new MappingJackson2HttpMessageConverter(mapper))
            .addFilters(new ServiceAuthFilter(token, mapper)).build();
    }
    @Test void roleHeaderWithoutServiceAuthenticationCannotWrite() throws Exception {
        api.perform(post("/api/v1/tickets").header("X-User-ID", "demo-operator").header("X-User-Role", "operator"))
            .andExpect(status().isUnauthorized());
        verifyNoInteractions(service);
    }
    @Test void viewerCannotDecide() throws Exception {
        api.perform(post("/api/v1/approvals/" + UUID.randomUUID() + "/decision")
            .header("Authorization", "Bearer " + token).header("X-User-ID", "demo-viewer").header("X-User-Role", "viewer")
            .contentType(MediaType.APPLICATION_JSON).content("{\"decision\":\"approve\"}"))
            .andExpect(status().isForbidden());
        verifyNoInteractions(service);
    }
    @Test void ownerCannotBeChosenInPayload() throws Exception {
        api.perform(post("/api/v1/approvals/" + UUID.randomUUID() + "/decision")
            .header("Authorization", "Bearer " + token).header("X-User-ID", "demo-operator").header("X-User-Role", "operator")
            .contentType(MediaType.APPLICATION_JSON).content("{\"decision\":\"approve\",\"owner_id\":\"other\"}"))
            .andExpect(status().isUnprocessableEntity());
        verifyNoInteractions(service);
    }
    @Test void draftValidationRejectsBlankAndInvalidPriority() {
        assertThrows(ApiException.class, () -> new ApprovalModels.Draft("INC-1", " ", "body", "team", "P1"));
        assertThrows(ApiException.class, () -> new ApprovalModels.Draft("INC-1", "title", "body", "team", "P9"));
        assertThrows(ApiException.class, () -> new ApprovalModels.Decision("auto-approve"));
    }
    @Test void hashIsStableForCanonicalDraft() {
        var s = new ApprovalService(null, new ObjectMapper(), 900);
        var a = new ApprovalModels.Draft("INC-1", " title ", "body", "team", "P1");
        var b = new ApprovalModels.Draft("INC-1", "title", "body", "team", "P1");
        assertEquals(ApprovalService.hash(s.canonical(a)), ApprovalService.hash(s.canonical(b)));
        assertNotEquals(ApprovalService.hash(s.canonical(a)), ApprovalService.hash(s.canonical(
            new ApprovalModels.Draft("INC-1", "different", "body", "team", "P1"))));
    }
}
