## The big picture first

This is a **`docker-compose.yml`** — while a Dockerfile builds *one* image, docker-compose orchestrates *multiple* containers together as one connected system: how they start, talk to each other, share data, and depend on one another. This one defines a 4-service stack: a database, a cache, an ML experiment tracker, and your API.

---

## Top-level structure

```yaml
services:
volumes:
networks:
```
Every compose file generally has these three sections:
- **`services`** — the actual containers to run
- **`volumes`** — named persistent storage that survives container restarts/removal
- **`networks`** — virtual networks so containers can find and talk to each other by name

---

## Service 1: `postgres`

```yaml
postgres:
  image: postgres:16-alpine
```
Pulls a pre-built **official Postgres image** (version 16, Alpine-based for small size) — no custom Dockerfile needed since Postgres doesn't need customization here.

```yaml
  container_name: risk_engine_postgres
  restart: unless-stopped
```
- `container_name` — gives it a fixed, human-readable name instead of Docker's auto-generated one (like `docker-compose_postgres_1`).
- `restart: unless-stopped` — if the container crashes or the host reboots, Docker restarts it automatically — *unless* you manually stopped it yourself.

```yaml
  environment:
    POSTGRES_USER: ${POSTGRES_USER:-fraud_user}
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-admin}
    POSTGRES_DB: ${POSTGRES_DB:-fraud_risk}
```
Sets environment variables the **official Postgres image** reads on first startup to auto-create a user/database. The `${VAR:-default}` syntax means: *"use the `POSTGRES_USER` value from my `.env` file or shell environment if it's set, otherwise fall back to `fraud_user`."* This makes the file portable across dev/staging/prod without editing the compose file itself.

**Worth flagging if asked:** `admin` as a default password is fine for local dev but should never survive into production — it should always be overridden via `.env` or secrets management.

```yaml
  ports:
    - "${POSTGRES_PORT:-5432}:5432"
```
Format is `"HOST_PORT:CONTAINER_PORT"`. This exposes Postgres on your **host machine** at port 5432 (or whatever `POSTGRES_PORT` is set to), mapped to port 5432 *inside* the container. This lets you connect from outside Docker too (e.g., a local DB GUI tool) — not just from other containers.

```yaml
  volumes:
    - postgres_data:/var/lib/postgresql/data
```
Mounts the **named volume** `postgres_data` (declared at the bottom of the file) to Postgres's actual data directory inside the container. This is critical: without it, all your database data would vanish the moment the container is removed, since container filesystems are ephemeral by default.

```yaml
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-fraud_user} -d ${POSTGRES_DB:-fraud_risk}"]
    interval: 10s
    timeout: 5s
    retries: 5
```
Uses Postgres's own `pg_isready` utility to check if the database is actually ready to accept connections — not just "container started," but "database is truly usable." This matters a lot here, because other services (`api`) will wait on this health status before starting (more below).

```yaml
  networks:
    - risk_network
```
Attaches this container to the custom `risk_network` (defined at the bottom), so it can be reached by other services using the hostname `postgres`.

---

## Service 2: `redis`

Structurally almost identical to Postgres:
```yaml
redis:
  image: redis:7-alpine
  ...
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
```
Redis here is likely used as a **cache** (fast lookups, e.g., caching model predictions or feature values) — common in risk-scoring APIs where you want sub-millisecond repeat lookups instead of always hitting Postgres. The healthcheck simply runs `redis-cli ping`, which returns `PONG` if the server is alive — the standard Redis liveness check.

---

## Service 3: `mlflow`

```yaml
mlflow:
  build:
    context: .
    dockerfile: docker/Dockerfile.mlflow
```
Unlike Postgres/Redis, this one is **built from a custom Dockerfile** (`docker/Dockerfile.mlflow`, not shown here) rather than pulled as a pre-built image — meaning the project has custom setup for MLflow (likely installing `mlflow` plus dependencies).

**MLflow**, if you're not familiar, is an open-source tool for **tracking ML experiments**: logging model metrics, parameters, and versioned model artifacts, so your training pipeline and this API can both reference "which model version is currently in production."

```yaml
  volumes:
    - ./mlflow.db:/mlflow/mlflow.db
    - ./mlruns:/mlflow/artifacts
```
Here's a difference from the named volumes above: these are **bind mounts** (`./local/path:/container/path`), not named volumes. They map specific files/folders from your **host project directory** directly into the container:
- `mlflow.db` — likely a SQLite database file storing experiment metadata
- `mlruns` — the directory storing logged model artifacts

**If asked "named volume vs bind mount, what's the difference?"** → A *named volume* (like `postgres_data`) is managed entirely by Docker in its own storage area — you don't need to know exactly where. A *bind mount* (like `./mlruns:/mlflow/artifacts`) points to a specific folder in your project on your actual host filesystem, so you can browse/edit those files directly outside Docker too.

```yaml
  environment:
    - MLFLOW_TRACKING_URI=http://0.0.0.0:5000
```
Tells the MLflow server itself which address to bind to internally.

```yaml
  healthcheck:
    test: ["CMD-SHELL", "curl -f http://localhost:5000/health || exit 1"]
```
Same pattern as the `Dockerfile.api` healthcheck you saw earlier — curl hitting a `/health` endpoint.

---

## Service 4: `api` — this is your FastAPI service from before

```yaml
api:
  build:
    context: .
    dockerfile: docker/Dockerfile.api
```
This is exactly the Dockerfile you reviewed earlier — `context: .` means "build using the project root as the build context" (so `COPY api/ /app/api/` etc. resolve relative to the repo root), and `dockerfile:` points to that specific file.

```yaml
  environment:
    - DATABASE_URL=postgresql://${POSTGRES_USER:-fraud_user}:${POSTGRES_PASSWORD:-admin}@postgres:5432/${POSTGRES_DB:-fraud_risk}
    - REDIS_URL=redis://redis:6379/0
    - MLFLOW_TRACKING_URI=http://mlflow:5000
```
This is the key piece that ties the whole stack together — **service discovery by name**. Notice the hostnames used: `postgres`, `redis`, `mlflow` — these aren't IP addresses, they're the **service names** defined above. Docker Compose automatically creates internal DNS entries on `risk_network` so any container can reach another simply by its service name. This only works because all four services share `networks: - risk_network`.

```yaml
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
    mlflow:
      condition: service_healthy
```
This is the most important orchestration detail in the whole file. A plain `depends_on: [postgres]` only waits for the container to **start** — not for the database inside to actually be ready. Using `condition: service_healthy` makes the `api` container wait until each dependency's **healthcheck** passes (the `pg_isready`, `redis-cli ping`, and MLflow `/health` checks defined above) before the API even attempts to start. This directly prevents a common bug: the API crashing on startup because it tried to connect to a database that technically existed but wasn't accepting connections yet.

```yaml
  volumes:
    - ./models:/app/models
    - ./configs:/app/configs
    - ./logs:/app/logs
```
Bind mounts again — these let you update trained model files or config on your host machine and have the running container see the changes without rebuilding the image. Handy in development; in production you'd more often bake `models/` into the image itself for immutability (as the Dockerfile's `COPY models/ /app/models/` actually does — worth noting there's slight redundancy/overlap here between what's baked into the image and what's mounted at runtime).

```yaml
  healthcheck:
    test: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
```
Same healthcheck logic as the `HEALTHCHECK` instruction inside `Dockerfile.api` — defined twice, once at the image level (so it works even if you run the container standalone outside compose) and once here (so compose can track and act on its health status too).

---

## Bottom sections

```yaml
volumes:
  postgres_data:
  redis_data:
```
Declares the two named volumes referenced above. Declaring them here (even empty) is what makes them Docker-managed persistent volumes rather than throwaway container storage.

```yaml
networks:
  risk_network:
    driver: bridge
```
Defines the custom network. `bridge` is the standard driver for a single-host, isolated virtual network — the default and most common choice for local/multi-container setups like this.

---

## How this connects to the Dockerfile from before

| From Dockerfile.api | How it's used in compose |
|---|---|
| `EXPOSE 8000` | Compose actually publishes it via `ports: "8000:8000"` |
| `HEALTHCHECK ... curl .../health` | Compose's `depends_on: condition: service_healthy` on *other* services relies on this same pattern being present on `mlflow` and implicitly checks `api`'s own health too |
| `ENV PYTHONPATH=/app` | Redundantly also set in compose's `environment:` — harmless, but technically duplicate |
| `COPY models/ /app/models/` (baked into image) | Compose also bind-mounts `./models:/app/models` at runtime — the bind mount will override/shadow the baked-in copy while running |

## Quick mental model to explain this to someone else

> "This compose file starts 4 containers: a Postgres database, a Redis cache, an MLflow tracking server, and my FastAPI app. They all sit on the same virtual network and reach each other by service name instead of IP. The API won't even attempt to start until Postgres, Redis, and MLflow all report themselves as *actually healthy* — not just running — which avoids race conditions on startup."