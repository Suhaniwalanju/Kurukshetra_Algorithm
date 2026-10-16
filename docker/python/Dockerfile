FROM python:3.12-slim

# Create non-root runner user
RUN groupadd -g 1001 runner && \
    useradd -u 1001 -g runner -m -s /bin/bash runner

# Pre-install and cache pytest and common test dependencies offline
RUN pip install --no-cache-dir pytest==8.3.4 pytest-timeout==2.3.1

USER runner
WORKDIR /workspace

# Default command
CMD ["python3", "-W", "error::DeprecationWarning", "main.py"]
