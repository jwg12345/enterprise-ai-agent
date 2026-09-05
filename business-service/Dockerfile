FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /workspace
COPY business-service/pom.xml ./

COPY business-service/src ./src
RUN --mount=type=cache,target=/root/.m2 mvn -B -ntp package
FROM eclipse-temurin:21-jre-jammy
WORKDIR /app
COPY --from=build /workspace/target/business-service-0.1.0.jar app.jar
RUN useradd --create-home app
USER app
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
