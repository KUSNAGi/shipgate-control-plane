FROM python:3.12-slim AS builder
WORKDIR /build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
COPY pyproject.toml README.md ./
COPY shipgate ./shipgate
RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-index --find-links=/wheels shipgate-control-plane && rm -rf /wheels
WORKDIR /app
COPY alembic.ini ./
COPY alembic ./alembic
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "shipgate.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"]
