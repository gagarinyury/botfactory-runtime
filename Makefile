dev:
	docker compose up -d --build

logs:
	docker compose logs -f runtime

down:
	docker compose down

psql:
	docker compose exec -it pg psql -U dev -d botfactory

test:
	docker compose exec -T runtime pytest -q

testv:
	docker compose exec -T runtime pytest -v

test-chaos:
	./scripts/chaos-helper.sh all

test-chaos-postgres:
	./scripts/chaos-helper.sh postgres 30

test-chaos-redis:
	./scripts/chaos-helper.sh redis 30

test-chaos-network:
	./scripts/chaos-helper.sh network 100ms 30

test-chaos-full:
	./scripts/chaos-helper.sh full

test-llm-stress:
	docker compose exec -T runtime python -m pytest tests/llm_stress/ -v

test-unit:
	docker compose exec -T runtime python -m pytest tests/unit/ -v

test-smoke:
	./scripts/smoke-test.sh

lint:
	docker compose exec -T runtime ruff check runtime/
	docker compose exec -T runtime black --check runtime/

typecheck:
	docker compose exec -T runtime mypy runtime/

.PHONY: dev logs down psql test testv test-chaos test-llm-stress test-unit test-smoke lint typecheck