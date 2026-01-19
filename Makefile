.PHONY: dev test install clean

# Development commands
dev:
	python -m src.main --nr 52000 --dev --dry-run

dev-range:
	python -m src.main --start 52000 --end 52010 --dev

dev-write:
	python -m src.main --nr 52000 --dev --write-supabase

# Tests
test:
	pytest tests/ -v

test-gating:
	pytest tests/test_gating.py -v

test-jsinfos:
	pytest tests/test_jsinfos.py -v

test-basket:
	pytest tests/test_basket.py -v

test-redact:
	pytest tests/test_redact.py -v

# Installation
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt
	pip install pytest pytest-cov

# Docker
docker-dev:
	docker-compose -f docker-compose.dev.yml up --build

docker-prod:
	docker-compose -f docker-compose.prod.yml up -d

docker-logs:
	docker-compose logs -f

# Clean
clean:
	find . -type d -name __pycache__ -exec rm -r {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf data/dev/*

clean-all: clean
	rm -rf data/spool/*
	rm -f data/state.db

cleanup-spool:
	python -m src.store.spool_cleanup --older-than-days 7

