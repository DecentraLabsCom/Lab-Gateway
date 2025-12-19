# Guacamole 1.6.0 relies on javax.servlet, so keep it on Tomcat 9 (Jakarta/Servlet 4) with Java 11.
FROM tomcat:11.0-jdk11-temurin

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Download Guacamole WAR 1.6.0
ADD https://archive.apache.org/dist/guacamole/1.6.0/binary/guacamole-1.6.0.war /usr/local/tomcat/webapps/guacamole.war

# Create Guacamole directories
RUN mkdir -p /etc/guacamole/extensions /etc/guacamole/lib

# Copy extensions and libraries
COPY extensions/*.jar /etc/guacamole/extensions/
COPY lib/*.jar /etc/guacamole/lib/

# Copy entrypoint script (generates guacamole.properties at runtime)
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Create symlink after everything is in place
RUN ln -sf /etc/guacamole /usr/local/tomcat/.guacamole

# Verify extensions are present (for debugging during build)
RUN echo "=== Installed Extensions ===" && \
    ls -lh /etc/guacamole/extensions/ && \
    echo "=== Installed Libraries ===" && \
    ls -lh /etc/guacamole/lib/

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
