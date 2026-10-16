FROM postgres:16.6-alpine

# Configure isolated environment
ENV POSTGRES_USER=runner
ENV POSTGRES_PASSWORD=runnerpass
ENV POSTGRES_DB=studio_sandbox
ENV PGDATA=/tmp/pgdata

# Create directory with permissions for runner
RUN mkdir -p /tmp/pgdata && \
    chown -R postgres:postgres /tmp/pgdata /workspace 2>/dev/null || true

USER postgres
WORKDIR /workspace

CMD ["postgres"]
