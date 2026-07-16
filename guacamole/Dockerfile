# Guacamole 1.6.0 relies on javax.servlet, so keep it on Tomcat 9 (Jakarta/Servlet 4) with Java 11.
FROM tomcat:9.0-jdk11-temurin

# Install curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*

# Download Guacamole WAR from the immutable Apache archive and verify it before
# it enters the image. The checksum is reviewed whenever GUACAMOLE_VERSION is
# changed; an unverified remote ADD is intentionally not used here.
ARG GUACAMOLE_VERSION=1.6.0
ARG GUACAMOLE_WAR_SHA256=b41ceb1e2df010b54db563e0b00edb8d5fe9f073c6168462e4c978df0fc6e716
ARG GUACAMOLE_BAN_SHA256=b4c4a2d73d3f66083c46d05409e3dea6f560579d3cf9c3ca3bf099aad7040aca
RUN curl -fsSL \
      "https://archive.apache.org/dist/guacamole/${GUACAMOLE_VERSION}/binary/guacamole-${GUACAMOLE_VERSION}.war" \
      -o /usr/local/tomcat/webapps/guacamole.war \
    && echo "${GUACAMOLE_WAR_SHA256}  /usr/local/tomcat/webapps/guacamole.war" | sha256sum -c -

# Create Guacamole directories
RUN mkdir -p /etc/guacamole/extensions /etc/guacamole/lib

# Install the official Guacamole 1.6 brute-force protection extension. The
# archive is pinned and verified before the JAR enters the image; keeping this
# in the custom Tomcat image preserves the same protection as the official
# Guacamole container rather than relying on an unreviewed runtime download.
RUN mkdir -p /tmp/guacamole-auth-ban \
    && curl -fsSL \
      "https://archive.apache.org/dist/guacamole/${GUACAMOLE_VERSION}/binary/guacamole-auth-ban-${GUACAMOLE_VERSION}.tar.gz" \
      -o /tmp/guacamole-auth-ban.tar.gz \
    && echo "${GUACAMOLE_BAN_SHA256}  /tmp/guacamole-auth-ban.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/guacamole-auth-ban.tar.gz -C /tmp/guacamole-auth-ban \
    && cp "/tmp/guacamole-auth-ban/guacamole-auth-ban-${GUACAMOLE_VERSION}/guacamole-auth-ban-${GUACAMOLE_VERSION}.jar" \
      /etc/guacamole/extensions/ \
    && rm -rf /tmp/guacamole-auth-ban /tmp/guacamole-auth-ban.tar.gz

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
