# Build from the repository root: the workspace lockfile lives there.
#   minikube image build -t <user>/mewlytics-catalog:dev -f services/catalog/Dockerfile .

FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

FROM python:3.12-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS builder
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app

# Dependencies first, so this layer is reused until the lockfile changes
COPY pyproject.toml uv.lock ./
COPY services/catalog/pyproject.toml services/catalog/
RUN uv sync --frozen --no-dev --package catalog --no-install-workspace

# The service itself, installed as a regular package rather than editable
COPY services/catalog/src services/catalog/src
RUN uv sync --frozen --no-dev --package catalog --no-editable

# Same base image as the builder: the venv links to its Python interpreter
FROM python:3.12-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
# Numeric user, so Kubernetes can check runAsNonRoot
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "catalog.main:app", "--host", "0.0.0.0", "--port", "8000"]
