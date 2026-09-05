package com.example.business.incident;

import java.nio.file.Path;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
import org.springframework.beans.factory.annotation.Value;

@Component
@Profile("seed")
public class SeedRunner implements CommandLineRunner {
    private final FixtureSeeder seeder;
    private final String path;
    public SeedRunner(FixtureSeeder seeder, @Value("${FIXTURE_PATH}") String path) {
        this.seeder = seeder; this.path = path;
    }
    public void run(String... args) throws Exception {
        System.out.println("Synthetic incidents inserted: " + seeder.seed(Path.of(path)));
    }
}
