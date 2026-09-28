# RAG Chatbot

1 web app RAG chatbot cho phép người dùng quản lý KB đơn giản bằng cách upload file pdf, txt, docx. Người dùng có thể chat với AI dựa trên KB đã upload.

## Requirements

- Đăng ký, đăng nhập
- Rate limit với người dùng
- Mỗi người dùng đều có 1 usage limit cố định
- Cho phép người dùng upload file pdf, text, docx. Các loại file khác không cho phép
- Ingest pdf thành md trước khi feed cho LLM
- Trò chuyện với chatbot về KB đã upload, có trích dẫn thuộc file nào
- Lưu conversation history
- Dockerfile cho frontend, backend. docker-compose cho cả project

ví dụ Dockerfile:
```Dockerfile
# ============================================================
# ADVANCED Dockerfile — Multi-stage build
#
# Mục tiêu: image < 500 MB, secure, production-ready
#
# Tại sao multi-stage?
#   Stage 1 (builder): cần pip, gcc, build tools để compile deps
#   Stage 2 (runtime): chỉ cần Python và site-packages → nhỏ và sạch
# ============================================================

# ──────────────────────────────────────────────────────────
# STAGE 1: Builder
# Cài đặt tất cả dependencies
# Image này KHÔNG được dùng để deploy
# ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Cài build dependencies (cần cho một số packages như numpy)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy và cài requirements
# Dùng --user để install vào /root/.local (dễ copy sang stage 2)
COPY 02-docker/production/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# ──────────────────────────────────────────────────────────
# STAGE 2: Runtime
# Chỉ copy những gì cần để CHẠY, không cần để BUILD
# ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Tạo non-root user — security best practice
# Chạy với root trong container là bad practice
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Copy installed packages từ builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy source code
COPY 02-docker/production/main.py .

# Copy utils from project root
RUN mkdir -p /app/utils
COPY utils/mock_llm.py /app/utils/mock_llm.py

# Đặt ownership cho appuser
RUN chown -R appuser:appuser /app

# Chuyển sang non-root user
USER appuser

# PATH để Python tìm được packages của --user install
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Health check — Docker sẽ tự restart nếu fail
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Start command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

# ============================================================
# Build commands (from project root):
#   cd ../../  # Go to project root
#   docker build -f 02-docker/production/Dockerfile -t agent-production .
#   docker images agent-production  ← kiểm tra size
#   docker run -p 8000:8000 -e ENVIRONMENT=production agent-production
# ============================================================
```

ví dụ docker-compose file

```yml
# ============================================================
# Docker Compose — Full Agent Stack
#
# Services:
#   1. agent    — FastAPI AI agent (2 replicas)
#   2. redis    — Cache cho session và rate limiting
#   3. qdrant   — Vector database cho RAG
#   4. nginx    — Reverse proxy, load balancer
#
# Chạy: docker compose up
# Test:  curl http://localhost/health
# Stop:  docker compose down
# ============================================================

version: "3.9"

services:

  # ──────────────────────────────────────
  # Agent Service
  # ──────────────────────────────────────
  agent:
    build:
      context: ../..             # build từ project root (Dockerfile dùng path từ root)
      dockerfile: 02-docker/production/Dockerfile
      target: runtime          # chỉ build stage "runtime", không build "builder"
    environment:
      - ENVIRONMENT=staging
      - PORT=8000
      - REDIS_URL=redis://redis:6379/0
      - QDRANT_URL=http://qdrant:6333
      # ❌ KHÔNG đặt secrets trực tiếp ở đây trong production
      # ✅ Dùng: docker secret hoặc env file ngoài git
    env_file:
      - .env.local              # secrets riêng, trong .gitignore
    depends_on:
      redis:
        condition: service_healthy
      qdrant:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c",
             "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    restart: unless-stopped
    # Không expose port trực tiếp — dùng qua Nginx
    networks:
      - internal

  # ──────────────────────────────────────
  # Redis — Session cache & Rate limiting
  # ──────────────────────────────────────
  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
    networks:
      - internal

  # ──────────────────────────────────────
  # Qdrant — Vector database
  # ──────────────────────────────────────
  qdrant:
    image: qdrant/qdrant:v1.9.0
    volumes:
      - qdrant_data:/qdrant/storage
    healthcheck:
      # curl không có trong image qdrant → dùng bash /dev/tcp thay thế
      test: ["CMD-SHELL", "bash -c 'echo > /dev/tcp/localhost/6333'"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 10s
    networks:
      - internal

  # ──────────────────────────────────────
  # Nginx — Reverse proxy & Load balancer
  # ──────────────────────────────────────
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"      # HTTP
      - "443:443"    # HTTPS (cần cert)
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - agent
    restart: unless-stopped
    networks:
      - internal

# ──────────────────────────────────────
# Volumes — persistent data
# ──────────────────────────────────────
volumes:
  redis_data:
  qdrant_data:

# ──────────────────────────────────────
# Network — isolate internal traffic
# ──────────────────────────────────────
networks:
  internal:
    driver: bridge
```

## Project structure

- `app/backend/`: nghiệp vụ, ingest, rag
- `app/frontend/`: giao diện web
- `nginx/`: cấu hình nginx

## Tech stack

- Backend: FastAPI, MongoDB, OpenAI API, docling(ingest)
- Frontend: Nextjs

## Các màn hình

- Đăng ký/đăng nhập
- Quản lý KB: show danh sách các file đã upload, có chức năng xóa, tải về, xem chi tiết
- Màn hình chat: show lịch sử từng session, chat bằng text đơn giản, trả về kèm trích dẫn

## CI/CD

- Sử dụng github actions
- Thêm 1 job để build image frontend và backend, sau đó push lên dockerhub registry

ví dụ:
```yml
name: Deploy to Lightsail

on:
  push:
    branches: [ "main" ]

jobs:
  deploy:
    runs-on: [self-hosted, lightsail]
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Create Env Files
        run: |
          echo "MONGODB_URI=${{ secrets.MONGODB_URI }}" > backend.env
          echo "JWT_SECRET=${{ secrets.JWT_SECRET }}" >> backend.env
          echo "GOOGLE_CLIENT_ID=${{ secrets.GOOGLE_CLIENT_ID }}" >> backend.env
          echo "ALLOWED_ORIGINS=${{ secrets.ALLOWED_ORIGINS }}" >> backend.env
          
          echo "NEXT_PUBLIC_API_URL=${{ secrets.NEXT_PUBLIC_API_URL }}" > frontend.env
          echo "NEXT_PUBLIC_GOOGLE_CLIENT_ID=${{ secrets.NEXT_PUBLIC_GOOGLE_CLIENT_ID }}" >> frontend.env

      - name: Deploy with Docker Compose
        env:
          DOCKERHUB_USERNAME: ${{ secrets.DOCKERHUB_USERNAME }}
          DOCKERHUB_BACKEND_REPO: ${{ secrets.DOCKERHUB_BACKEND_REPO }}
          DOCKERHUB_FRONTEND_REPO: ${{ secrets.DOCKERHUB_FRONTEND_REPO }}
        run: |
          docker compose -f deployment/docker/docker-compose.yml down
          docker compose -f deployment/docker/docker-compose.yml pull
          docker compose -f deployment/docker/docker-compose.yml up -d
          docker image prune -f

```