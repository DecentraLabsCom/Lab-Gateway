FROM python:3.12-alpine

WORKDIR /app

RUN apk add --no-cache wget && \
    pip install --no-cache-dir flask==3.1.0

COPY server.py .

EXPOSE 5001

CMD ["python", "server.py"]
