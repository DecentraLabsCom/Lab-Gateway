# Logging Configuration

## 📋 Log Configuration Summary

| Service       | Max Size | Max Files | Total Storage | Description                     |
| ------------- | -------- | --------- | ------------- | ------------------------------- |
| **MySQL**     | 10MB     | 3         | \~30MB        | Database logs and queries       |
| **Guacd**     | 5MB      | 3         | \~15MB        | Protocol daemon logs            |
| **Guacamole** | 20MB     | 5         | \~100MB       | Application logs (most verbose) |
| **OpenResty** | 10MB     | 5         | \~50MB        | Access logs and proxy logs      |

**Total Maximum Log Storage**: \~195MB

## 🔍 Useful Logging Commands

### View Live Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f openresty
docker-compose logs -f guacamole
docker-compose logs -f mysql
docker-compose logs -f guacd

# Last N lines
docker-compose logs --tail=50 openresty
```

### Filter Logs by Time

```bash
# Since timestamp
docker-compose logs mysql --since="2024-01-01T10:00:00"

# Last 10 minutes
docker-compose logs guacamole --since="10m"

# Last hour
docker-compose logs --since="1h"
```

### Search in Logs

```bash
# PowerShell - Search for errors
docker-compose logs | Select-String -Pattern "error|failed|exception" -CaseSensitive:$false

# PowerShell - Search for specific patterns
docker-compose logs openresty | Select-String -Pattern "JWT|auth|token"
docker-compose logs mysql | Select-String -Pattern "connection|query"
```

### Log File Locations

Log files are stored in Docker's default location:

* **Windows**: `C:\ProgramData\docker\containers\<container-id>\<container-id>-json.log`
* **Linux**: `/var/lib/docker/containers/<container-id>/<container-id>-json.log`

### Export Logs

```bash
# Export all logs to file
docker-compose logs > gateway-logs-$(Get-Date -Format "yyyy-MM-dd").log

# Export specific service logs
docker-compose logs openresty > openresty-logs-$(Get-Date -Format "yyyy-MM-dd").log
```

## ⚠️ Log Rotation

The logging configuration automatically rotates logs when:

* File size exceeds the `max-size` limit
* Number of files exceeds `max-file` limit

Oldest logs are automatically deleted to maintain storage limits.

## 🔧 Advanced Logging Options

### Enable Debug Logging (Development)

Add to specific service in docker-compose.yml:

```yaml
environment:
  - LOG_LEVEL=DEBUG
```

### Send Logs to External System

For production, consider:

* **Fluentd**: For centralized logging
* **ELK Stack**: Elasticsearch, Logstash, Kibana
* **Splunk**: Enterprise logging solution

Example with Fluentd:

```yaml
logging:
  driver: "fluentd"
  options:
    fluentd-address: "localhost:24224"
    tag: "gateway.{{.Name}}"
```

## 🚨 Log Monitoring

### Critical Patterns to Monitor

* `ERROR`, `FATAL`, `CRITICAL`
* `Authentication failed`
* `Connection refused`
* `Out of memory`
* `Database connection lost`
* `SSL/TLS errors`

### Health Check via Logs

```bash
# Check for recent errors (last 5 minutes)
docker-compose logs --since="5m" | Select-String -Pattern "error|failed|fatal" -CaseSensitive:$false
```

## 📈 Log Analysis

### Common Log Queries

```bash
# Count error occurrences
docker-compose logs | Select-String -Pattern "error" -CaseSensitive:$false | Measure-Object

# Find authentication attempts
docker-compose logs openresty | Select-String -Pattern "JWT|auth" -CaseSensitive:$false

# Monitor MySQL performance
docker-compose logs mysql | Select-String -Pattern "slow query|performance|timeout"
```
