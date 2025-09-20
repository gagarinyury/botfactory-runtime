dev:
	docker compose up -d --build

logs:
	docker compose logs -f runtime

down:
	docker compose down

psql:
	docker compose exec -it pg psql -U dev -d botfactory

.PHONY: dev logs down psql