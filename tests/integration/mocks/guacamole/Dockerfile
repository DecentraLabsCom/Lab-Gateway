FROM python:3.12-alpine

WORKDIR /app

RUN pip install --no-cache-dir flask==3.1.0

COPY server.py .

EXPOSE 8080

CMD ["python", "server.py"]
