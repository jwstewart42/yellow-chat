ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base:3.24
FROM $BUILD_FROM

RUN apk add --no-cache python3

ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY app/ /app/
COPY run.sh /

CMD ["/run.sh"]
