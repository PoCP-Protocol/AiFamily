.DEFAULT_GOAL := help
PY := uv run --python 3.12

.PHONY: help setup test arch lint fmt check

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
