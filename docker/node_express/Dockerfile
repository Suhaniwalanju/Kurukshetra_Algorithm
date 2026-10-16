FROM node:20.18.0-bookworm-slim

# Create non-root runner user
RUN groupadd -g 1001 runner && \
    useradd -u 1001 -g runner -m -s /bin/bash runner

# Pre-install Express and test harness dependencies offline
WORKDIR /usr/local/lib/studio-node
RUN npm init -y && \
    npm install --no-audit --no-fund express@4.21.2 supertest@7.0.0

ENV NODE_PATH="/usr/local/lib/studio-node/node_modules"

USER runner
WORKDIR /workspace

CMD ["node", "server.js"]
