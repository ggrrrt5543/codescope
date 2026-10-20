FROM mcr.microsoft.com/dotnet/sdk:8.0-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv nodejs g++ cppcheck openjdk-17-jdk-headless \
    && rm -rf /var/lib/apt/lists/*
ENV PATH="/opt/venv/bin:${PATH}" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1 HOME=/tmp
WORKDIR /app
COPY . /app
RUN python3 -m venv /opt/venv && pip install --no-cache-dir -r requirements-lock.txt \
    && pip install --no-cache-dir --no-deps . \
    && useradd --uid 10001 --no-create-home codescope
USER 10001
EXPOSE 8765
CMD ["uvicorn", "codescope.app:app", "--host", "0.0.0.0", "--port", "8765", "--no-access-log"]
