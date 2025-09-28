# Multi-stage build for DecentraLabs Auth Service
FROM maven:3.9.6-eclipse-temurin-18 AS build

# Set working directory
WORKDIR /app

# Copy pom.xml first for better caching
COPY pom.xml .

# Download dependencies
RUN mvn dependency:go-offline -B

# Copy source code
COPY src ./src

# Build the application (WAR packaging as per your pom.xml)
RUN mvn clean package -DskipTests

# Runtime stage - Use Tomcat since your app is packaged as WAR
FROM tomcat:10.1-jdk18-temurin-jammy

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Remove default Tomcat applications
RUN rm -rf /usr/local/tomcat/webapps/*

# Copy the built WAR from build stage and deploy to ROOT context
COPY --from=build /app/target/*.war /usr/local/tomcat/webapps/auth.war

# Create directories for keys and certificates
RUN mkdir -p /usr/local/tomcat/keys

# Create non-root user for security
RUN groupadd -g 1001 authservice && \
    useradd -r -u 1001 -g authservice authservice && \
    chown -R authservice:authservice /usr/local/tomcat

# Switch to non-root user
USER authservice

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/auth/health || exit 1

# Set environment for Spring profiles
ENV SPRING_PROFILES_ACTIVE=docker

# Run Tomcat
CMD ["catalina.sh", "run"]