# Build from the repository root: the workspace lockfile lives there.
#   minikube image build -t <user>/mewlytics-catalog:dev -f services/catalog/Dockerfile .

FROM ghcr.io/astral-sh/uv:0.13.10@sha256:a3ea1357342c1a4bf9a0c53a3deb1b55379aefa037338d8113d5771efa01774f AS uv

FROM python:3.12-slim-trixie@sha256:5b5fe805d367f8f5a359ded6ab2652b7f9a206453ee6ee789c0045ba6ec15016 AS builder
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
FROM python:3.12-slim-trixie@sha256:5b5fe805d367f8f5a359ded6ab2652b7f9a206453ee6ee789c0045ba6ec15016
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
