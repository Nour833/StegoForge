FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-web.txt
COPY . .
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 stegoforge
USER stegoforge
EXPOSE 5000
ENV STEGOFORGE_OFFLINE=1
# The UI must listen on all interfaces inside a container, so it is token-protected by default:
# `docker logs` shows the generated token; pass -e STEGOFORGE_WEB_TOKEN=<secret> to choose your own.
ENV STEGOFORGE_WEB_TOKEN=auto
CMD ["stegoforge", "web", "--skip-banner", "--host", "0.0.0.0"]
