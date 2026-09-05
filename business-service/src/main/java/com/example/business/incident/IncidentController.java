package com.example.business.incident;

import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/incidents")
public class IncidentController {
    private final IncidentRepository repository;
    public IncidentController(IncidentRepository repository) { this.repository = repository; }
    @GetMapping
    public IncidentRepository.Page find(@RequestParam MultiValueMap<String,String> params) {
        return repository.find(IncidentQuery.parse(params));
    }
}
