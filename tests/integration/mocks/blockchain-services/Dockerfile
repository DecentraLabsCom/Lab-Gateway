FROM python:3.12-alpine

WORKDIR /app
RUN apk add --no-cache wget
COPY server.py /app/server.py

EXPOSE 8080

CMD ["python", "/app/server.py"]
