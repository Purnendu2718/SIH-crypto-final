.PHONY: up down seed test clean help

help:
	@echo "CryptoTrace Sentinel (SIH26183) Makefile"
	@echo "  make up     - Build and start all services via Docker Compose"
	@echo "  make down   - Stop and remove Docker Compose containers"
	@echo "  make seed   - Seed fixture and demo dataset into the database"
	@echo "  make test   - Run test suites for backend and frontend"
	@echo "  make clean  - Clean temporary build artifacts and caches"

up:
	docker compose up --build

down:
	docker compose down

seed:
	@echo "Seeding offline fixture dataset..."
	python -m backend.app.fixtures.seed_fixtures || echo "Seeding script hook ready for Phase 2."

test:
	@echo "Running backend test suite..."
	python -m pytest backend/tests -v
	@echo "Running frontend type check and build test..."
	cd frontend && npm run build

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	rm -rf frontend/dist frontend/node_modules/.vite
