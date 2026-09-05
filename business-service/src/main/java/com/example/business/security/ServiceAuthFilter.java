package com.example.business.security;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.UUID;
import com.example.business.common.Errors;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class ServiceAuthFilter extends OncePerRequestFilter {
    private static final Logger LOG = LoggerFactory.getLogger(ServiceAuthFilter.class);
    private final String token;
    private final ObjectMapper mapper;
    public ServiceAuthFilter(@Value("${BUSINESS_SERVICE_TOKEN}") String token, ObjectMapper mapper) {
        if (token.length() < 24) throw new IllegalArgumentException("서비스 인증 설정이 필요합니다.");
        this.token = token;
        this.mapper = mapper;
    }
    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String incoming = request.getHeader("X-Request-ID");
        String id = incoming != null && incoming.matches("[A-Za-z0-9-]{1,64}") ? incoming : UUID.randomUUID().toString();
        request.setAttribute("request_id", id);
        response.setHeader("X-Request-ID", id);
        long start = System.nanoTime();
        try {
            if (request.getRequestURI().startsWith("/api/")) {
                String auth = request.getHeader("Authorization");
                if (auth == null || !MessageDigest.isEqual(("Bearer " + token).getBytes(StandardCharsets.UTF_8), auth.getBytes(StandardCharsets.UTF_8))) {
                    reject(response, 401, "UNAUTHENTICATED", id); return;
                }
                String user = request.getHeader("X-User-ID"), role = request.getHeader("X-User-Role");
                if (!(("demo-viewer".equals(user) && "viewer".equals(role))
                        || ("demo-operator".equals(user) && "operator".equals(role)))) {
                    reject(response, 403, "FORBIDDEN", id); return;
                }
            }
            chain.doFilter(request, response);
        } finally {
            LOG.atInfo().addKeyValue("request_id", id).addKeyValue("service", "business")
                .addKeyValue("status", response.getStatus())
                .addKeyValue("duration_ms", (System.nanoTime() - start) / 1_000_000)
                .log("request_complete");
        }
    }
    private void reject(HttpServletResponse response, int status, String code, String id) throws IOException {
        response.setStatus(status);
        response.setContentType("application/json");
        response.setCharacterEncoding("UTF-8");
        mapper.writeValue(response.getWriter(), Errors.body(code, "인증 및 권한을 확인하세요.", false, id));
    }
}
