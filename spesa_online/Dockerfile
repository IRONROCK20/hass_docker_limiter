# Dockerfile
ARG BUILD_FROM=hassioaddons/base-python:5.2.0
FROM ${BUILD_FROM}

# Use bash with pipefail for better error handling
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# 1) Install Python requirements
COPY . /

ARG BUILD_ARCH=arm64

RUN pip install flask docker gunicorn requests

EXPOSE 9007

CMD ["gunicorn", "-b", "0.0.0.0:12000", "app:app"]