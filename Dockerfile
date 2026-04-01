FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY skills ./skills
COPY deploy ./deploy
COPY .env.example ./

RUN pip install --no-cache-dir .

CMD ["python", "-m", "agent_codex.apps.cli.main", "doctor"]
