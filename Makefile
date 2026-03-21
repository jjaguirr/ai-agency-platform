.PHONY: dashboard-install dashboard-build dashboard-dev serve test

dashboard-install:
	cd dashboard && npm ci

dashboard-build:
	cd dashboard && npm run build

dashboard-dev:
	cd dashboard && npm run dev

# Build the dashboard then start FastAPI serving it at / with the API at /v1/.
serve: dashboard-build
	uv run uvicorn src.api.app:create_default_app --factory --host 0.0.0.0 --port 8000

test:
	uv run pytest tests/unit/ -q
