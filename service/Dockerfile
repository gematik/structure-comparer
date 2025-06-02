FROM python:3.13-alpine AS builder

WORKDIR /build
COPY . .

RUN pip install poetry
RUN poetry build


FROM python:3.13-alpine

WORKDIR /app
COPY --from=builder /build/dist/*.whl ./structure_comparer-0.1.0-py3-none-any.whl
RUN pip install ./structure_comparer-0.1.0-py3-none-any.whl

ENV STRUCTURE_COMPARER_PROJECTS_DIR=/app/projects

ENTRYPOINT ["python", "-m", "structure_comparer", "serve"]
