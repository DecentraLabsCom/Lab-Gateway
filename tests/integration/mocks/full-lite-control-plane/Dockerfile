FROM python:3.12-alpine

WORKDIR /app

RUN apk add --no-cache wget && \
    pip install --no-cache-dir Flask==3.1.0 PyJWT==2.10.1 cryptography==44.0.0

COPY server.py /app/server.py

EXPOSE 8080

CMD ["python", "/app/server.py"]
