# VietDocAI

Backend OCR tài liệu tiếng Việt sử dụng FastAPI, Celery, RabbitMQ,
PostgreSQL và PaddleOCR.

## Khởi động

Yêu cầu Docker Engine và Docker Compose v2.

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
```

Kiểm tra dịch vụ:

```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

`/health/ready` kiểm tra cả PostgreSQL và RabbitMQ.

UI upload và xem kết quả OCR ở `http://localhost:8000/`.
Swagger UI ở `http://localhost:8000/docs`. Có thể tắt OpenAPI/Swagger
trong production bằng `DOCS_ENABLED=false`.

Schema database được quản lý bằng Alembic. Khi chạy bằng Compose, service
`migrate` sẽ chạy `alembic upgrade head` trước khi `api` và `worker` khởi động.

## API

Tạo OCR job:

```bash
curl -F "file=@/path/to/document.png" \
  http://localhost:8000/api/v1/documents
```

Lấy kết quả và danh sách gần nhất:

```bash
curl http://localhost:8000/api/v1/documents/<document_id>
curl "http://localhost:8000/api/v1/documents?limit=20"
```

Hỗ trợ JPG/JPEG, PNG, TIFF và PDF, tối đa 20 MB theo cấu hình mặc định.
Nếu đặt `API_KEY` trong `.env`, mọi endpoint `/api/v1/documents` yêu cầu
header `X-API-Key`. UI không hiển thị ô nhập key; khi public production nên đặt
auth/reverse proxy phù hợp thay vì để người dùng nhập key trong giao diện.

## Kiểm thử

Tạo virtual environment và cài dependency phát triển:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
pytest -q
```

Kiểm tra cấu hình và log container:

```bash
docker compose config -q
docker compose logs -f api worker
```

## Production checklist

- Thay toàn bộ password mẫu trong `.env` bằng secret mạnh.
- Đặt `APP_ENVIRONMENT=production` và `DOCS_ENABLED=false` nếu API docs
  không được bảo vệ.
- Đặt `API_KEY` hoặc thay bằng cơ chế auth đầy đủ trước khi public API.
- Không public trực tiếp cổng PostgreSQL, RabbitMQ và RabbitMQ management.
- Đặt reverse proxy/TLS, rate limiting và giới hạn request.
- Dùng object storage bền vững thay cho bind mount local khi triển khai nhiều node.
- Thiết lập backup PostgreSQL, monitoring, alerting và log tập trung.
- Pin/lock dependency và scan image trong CI trước khi phát hành.

Container ứng dụng chạy bằng user `appuser` (UID/GID 1000). Celery có soft
timeout và hard timeout; các giá trị được cấu hình trong `.env`.
Các service `api`, `worker` và `migrate` chạy với root filesystem read-only,
drop Linux capabilities, `no-new-privileges` và tmpfs riêng cho `/tmp`.
Document OCR lưu thêm mốc thời gian bắt đầu xử lý, hoàn tất và thất bại để
phục vụ vận hành/retry sau này.

## Deploy production trên VPS

File `docker-compose.yml` phục vụ local/dev nên có publish port PostgreSQL và
RabbitMQ để debug. Khi deploy public, dùng file production riêng:

```bash
cp .env.production.example .env.production
# Sửa toàn bộ secret trong .env.production trước khi chạy.
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.production ps
```

`docker-compose.prod.yml` chỉ bind API vào `127.0.0.1:8000`; PostgreSQL và
RabbitMQ không mở port ra host. Đặt Nginx/Caddy/Traefik phía trước để terminate
TLS và public domain.

Ví dụ Nginx tối thiểu:

```nginx
server {
    listen 80;
    server_name vietdocai.example.com;

    client_max_body_size 25m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Sau đó bật HTTPS bằng Certbot hoặc dùng Caddy để tự quản lý TLS. Nếu app public
cho người dùng thật, nên bảo vệ toàn bộ domain bằng auth ở reverse proxy
hoặc tích hợp đăng nhập riêng. `API_KEY` chỉ phù hợp cho API machine-to-machine;
UI hiện không yêu cầu người dùng nhập API key để giữ trải nghiệm production.

Kiểm tra sau deploy:

```bash
curl -fsS https://vietdocai.example.com/health/live
curl -fsS https://vietdocai.example.com/health/ready
docker compose -f docker-compose.prod.yml --env-file .env.production logs --tail=100 api worker
```

## CI/CD với GitHub Actions

Project có 2 workflow:

- `.github/workflows/ci.yml`: chạy khi push/PR vào `main` hoặc `master`.
  Workflow này cài dependency, chạy test, compile Python, validate Docker Compose
  dev/prod và build Docker image.
- `.github/workflows/deploy.yml`: deploy production thủ công bằng
  `workflow_dispatch`. Nên deploy thủ công trước; khi pipeline ổn có thể đổi
  sang tự động deploy khi push `main`.

Thiết lập GitHub Secrets cho workflow deploy:

| Secret | Ý nghĩa |
| --- | --- |
| `VPS_HOST` | IP hoặc hostname VPS |
| `VPS_PORT` | SSH port, có thể để `22` |
| `VPS_USER` | User deploy trên VPS |
| `VPS_SSH_KEY` | Private SSH key để GitHub Actions SSH vào VPS |
| `DEPLOY_PATH` | Đường dẫn repo trên VPS, ví dụ `/opt/vietdocai` |
| `PRODUCTION_ENV_FILE` | Nội dung đầy đủ của file `.env.production` |

Chuẩn bị VPS lần đầu:

```bash
sudo mkdir -p /opt/vietdocai
sudo chown "$USER":"$USER" /opt/vietdocai
git clone <your-repo-url> /opt/vietdocai
cd /opt/vietdocai
docker compose -f docker-compose.prod.yml --env-file .env.production config -q
```

Deploy bằng GitHub UI:

1. Vào repository trên GitHub.
2. Mở tab **Actions**.
3. Chọn workflow **Deploy**.
4. Bấm **Run workflow** và nhập ref cần deploy, mặc định là `main`.

Deploy workflow sẽ SSH vào VPS, ghi lại `.env.production` từ secret
`PRODUCTION_ENV_FILE`, kéo code mới nhất và chạy:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```
