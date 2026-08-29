.DEFAULT_GOAL := help
PY := uv run --python 3.12

.PHONY: help setup test arch lint fmt fmt-check check db-up db-down db-migrate test-pg

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

fmt-check: ## ruff 格式化差异检查（只读，不改文件）
	$(PY) -m ruff format --check .

# ADR-0009：全量 sweep 未完成前，CI 的格式检查是**警告级**。这里刻意与 CI 保持
# 一致 —— 若 `make check` 因格式差异而失败，本地就比 CI 更严，开发者会学会忽略
# `make check`，那比没有这个 target 更糟。sweep 收尾时把 fmt-check 加进下面的
# 依赖列表，并同步删掉 ci.yml 里那个 `|| true`。
check: lint test ## lint + test，CI 等价物（格式检查见 fmt-check，暂不阻断）

db-up: ## 起一次性开发 Postgres（等到 healthy）
	$(COMPOSE) up -d --wait

db-down: ## 停掉并删除开发 Postgres
	$(COMPOSE) down

db-migrate: db-up ## 对开发 Postgres 应用 Alembic baseline
	DATABASE_URL=$(PG_TEST_URL) $(PY) -m alembic upgrade head
	DATABASE_URL=$(PG_TEST_URL) $(PY) -m alembic current

test-pg: db-up ## 全量测试并打开真实 Postgres 路径（默认 make test 只跑 SQLite 快路径）
	AIFAMILY_TEST_DATABASE_URL=$(PG_TEST_URL) $(PY) -m pytest
