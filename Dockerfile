FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY lovecash ./lovecash
RUN uv sync --frozen --extra server --no-dev
EXPOSE 8080
ENTRYPOINT ["uv", "run", "lovecash"]
CMD ["serve", "--config", "/config/config.yaml"]
