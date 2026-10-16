FROM debian:bookworm-slim

# Create non-root runner user
RUN groupadd -g 1001 runner && \
    useradd -u 1001 -g runner -m -s /bin/bash runner

# Install gcc, libc-dev, and sanitizers
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      gcc \
      libc6-dev \
      libasan8 \
      libubsan1 \
      make && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

USER runner
WORKDIR /workspace

CMD ["./main"]
