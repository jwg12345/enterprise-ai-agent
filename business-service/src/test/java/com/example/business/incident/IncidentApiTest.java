package com.example.business.incident;

import com.example.business.common.Errors;
import com.example.business.security.ServiceAuthFilter;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.*;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.mockito.Mockito.*;

class IncidentApiTest {
    private MockMvc api;
    private IncidentRepository repository;
    @BeforeEach void setup() {
        repository = mock(IncidentRepository.class);
        api = MockMvcBuilders.standaloneSetup(new IncidentController(repository))
            .setControllerAdvice(new Errors())
            .addFilters(new ServiceAuthFilter("s".repeat(32), new ObjectMapper())).build();
    }
    @Test void untrustedUserHeaderIsRejected() throws Exception {
        api.perform(get("/api/v1/incidents").header("X-User-Role","operator"))
            .andExpect(status().isUnauthorized());
        verifyNoInteractions(repository);
    }
    @Test void serviceWithoutValidUserIsRejected() throws Exception {
        api.perform(get("/api/v1/incidents").header("Authorization","Bearer " + "s".repeat(32))
            .header("X-User-ID","demo-viewer").header("X-User-Role","operator"))
            .andExpect(status().isForbidden());
        verifyNoInteractions(repository);
    }
    @Test void invalidFilterReturnsContractError() throws Exception {
        api.perform(get("/api/v1/incidents").header("Authorization","Bearer " + "s".repeat(32))
            .header("X-User-ID","demo-viewer").header("X-User-Role","viewer")
            .header("X-Request-ID","test-123")
            .param("from","2026-08-01T00:00:00Z").param("to","2026-09-01T00:00:00Z").param("size","51"))
            .andExpect(status().isUnprocessableEntity()).andExpect(jsonPath("$.error.code").value("INVALID_QUERY"))
            .andExpect(header().string("X-Request-ID","test-123"));
        verifyNoInteractions(repository);
    }
}
