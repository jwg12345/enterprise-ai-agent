package com.example.business;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BusinessApplication {
    public static void main(String[] args) {
        var context = SpringApplication.run(BusinessApplication.class, args);
        if (java.util.Arrays.asList(context.getEnvironment().getActiveProfiles()).contains("seed")) {
            context.close();
        }
    }
}
