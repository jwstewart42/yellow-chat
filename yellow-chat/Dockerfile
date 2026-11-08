ARG BUILD_FROM
FROM $BUILD_FROM

ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY app/ /app/

CMD ["python3", "/app/server.py"]
