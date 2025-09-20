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

.PHONY: dev logs down psql test testv