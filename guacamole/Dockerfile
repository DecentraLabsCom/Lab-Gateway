FROM tomcat:9.0

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Download Guacamole WAR
ADD https://downloads.apache.org/guacamole/1.5.5/binary/guacamole-1.5.5.war /usr/local/tomcat/webapps/guacamole.war

# Create Guacamole directories
RUN mkdir -p /etc/guacamole/extensions
RUN ln -s /etc/guacamole /usr/local/tomcat/.guacamole

# Copy extensions and libraries
COPY extensions /etc/guacamole/extensions/
COPY lib /usr/local/tomcat/lib/

# Copy configuration
COPY guacamole.properties /etc/guacamole/

EXPOSE 8080
