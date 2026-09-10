FROM python:3.13-slim

WORKDIR /app

# System deps for Playwright chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir . playwright pydantic httpx redis pillow torch \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple \
    && pip install --no-cache-dir transformers pyyaml fastmcp \
    && python -m playwright install chromium --with-deps

ENV NOT_NOVA_ACT_PORT=8171 \
    NOT_NOVA_ACT_HOST=0.0.0.0 \
    NOT_NOVA_ACT_SCREENSHOT_DIR=/tmp/not-nova-act-shots

EXPOSE 8171

CMD ["python", "-m", "not_nova_act.server"]
