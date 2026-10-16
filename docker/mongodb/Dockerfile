FROM mongo:7.0.16-jammy

# Configure non-root user and directories
ENV MONGO_INITDB_DATABASE=studio_sandbox

RUN mkdir -p /data/db /workspace && \
    chown -R mongodb:mongodb /data/db /workspace

USER mongodb
WORKDIR /workspace

CMD ["mongosh", "--quiet", "--file", "script.js"]
