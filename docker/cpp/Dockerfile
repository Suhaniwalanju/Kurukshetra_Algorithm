FROM debian:bookworm-slim

# Create non-root runner user
RUN groupadd -g 1001 runner && \
    useradd -u 1001 -g runner -m -s /bin/bash runner

# Install g++ with C++20 support, sanitizers, and pre-cache doctest
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      g++ \
      libc6-dev \
      libasan8 \
      libubsan1 \
      curl \
      make && \
    mkdir -p /usr/local/include/doctest && \
    curl -fsSL https://raw.githubusercontent.com/doctest/doctest/v2.4.11/doctest/doctest.h \
      -o /usr/local/include/doctest/doctest.h && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

USER runner
WORKDIR /workspace

CMD ["./main"]
