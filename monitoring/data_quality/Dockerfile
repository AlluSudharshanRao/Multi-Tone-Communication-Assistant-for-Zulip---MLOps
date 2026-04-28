FROM python:3.11-slim

WORKDIR /app

COPY monitoring/data_quality /app

RUN pip install --no-cache-dir .

EXPOSE 9108

CMD ["zulip-data-quality-exporter", "--config", "config/data_quality.yaml"]
