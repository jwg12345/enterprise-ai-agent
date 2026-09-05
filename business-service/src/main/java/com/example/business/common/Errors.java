package com.example.business.common;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.dao.DataAccessException;

@RestControllerAdvice
public class Errors {
    public static Map<String, Object> body(String code, String message, boolean retryable, Object requestId) {
        return Map.of("error", Map.of("code", code, "message", message, "retryable", retryable),
                      "request_id", requestId == null ? "unavailable" : requestId);
    }
    @ExceptionHandler(ApiException.class)
    public ResponseEntity<?> api(ApiException ex, HttpServletRequest request) {
        return ResponseEntity.status(ex.status).body(body(ex.code, ex.getMessage(), false, request.getAttribute("request_id")));
    }
    @ExceptionHandler(DataAccessException.class)
    public ResponseEntity<?> database(DataAccessException ex, HttpServletRequest request) {
        return ResponseEntity.status(503).body(body("DATABASE_UNAVAILABLE", "업무 저장소에 연결할 수 없습니다.", true, request.getAttribute("request_id")));
    }
}
