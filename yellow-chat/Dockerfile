ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base-python:3.12-alpine3.18
FROM $BUILD_FROM

ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY app/ /app/
COPY rootfs /
