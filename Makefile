.DEFAULT_GOAL := help
PY := uv run --python 3.12

.PHONY: help setup test arch lint fmt check db-up db-down db-migrate test-pg

COMPOSE := docker compose -f docker-compose.dev.yml
# The host port lives in docker-compose.dev.yml; this must match it. Kept as one
# variable so `db-migrate` and `test-pg` cannot drift apart from each other.
PG_TEST_URL := postgresql+asyncpg://aifamily:aifamily@localhost:55442/aifamily_test

help: ## 显示可用命令
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n",$$1,$$2}'

setup: ## 创建虚拟环境并安装 dev 依赖
	uv venv --python 3.12
	uv pip install -e ".[dev]"

test: ## 运行全部测试
	$(PY) -m pytest

arch: ## 只运行架构测试（治理护栏）
	$(PY) -m pytest tests/architecture -v

lint: ## ruff 检查
	$(PY) -m ruff check .

fmt: ## ruff 格式化
	$(PY) -m ruff format .

check: lint test ## lint + test，CI 等价物

db-up: ## 起一次性开发 Postgres（等到 healthy）
	$(COMPOSE) up -d --wait

db-down: ## 停掉并删除开发 Postgres
	$(COMPOSE) down

db-migrate: db-up ## 对开发 Postgres 应用 Alembic baseline
	DATABASE_URL=$(PG_TEST_URL) $(PY) -m alembic upgrade head
	DATABASE_URL=$(PG_TEST_URL) $(PY) -m alembic current

test-pg: db-up ## 全量测试并打开真实 Postgres 路径（默认 make test 只跑 SQLite 快路径）
	AIFAMILY_TEST_DATABASE_URL=$(PG_TEST_URL) $(PY) -m pytest
