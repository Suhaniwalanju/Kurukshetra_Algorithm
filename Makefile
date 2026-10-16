.PHONY: images health test help

help:
	@echo "Available commands:"
	@echo "  make images  - Build all 10 language/runtime Docker images"
	@echo "  make health  - Perform health checks on all language runtime runners"
	@echo "  make test    - Run complete unit and integration test suite"

images:
	python scripts/build_images.py

health:
	python scripts/health_check.py

test:
	python -m pytest backend/tests -v
