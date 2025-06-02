FROM python:3.13-alpine AS builder

WORKDIR /build

RUN pip install poetry

COPY ./src ./src
COPY ./poetry.lock .
COPY ./pyproject.toml .
COPY README.md .

RUN poetry build


FROM python:3.13-alpine

RUN apk add curl

WORKDIR /app
COPY --from=builder /build/dist/*.whl ./structure_comparer-0.1.0-py3-none-any.whl
RUN pip install ./structure_comparer-0.1.0-py3-none-any.whl

ENV STRUCTURE_COMPARER_PROJECTS_DIR=/app/projects

HEALTHCHECK --interval=30s --timeout=90s --start-period=30s --retries=3 CMD curl http://127.0.0.1:8000/ || exit 1
ENTRYPOINT ["python", "-m", "structure_comparer", "serve"]
