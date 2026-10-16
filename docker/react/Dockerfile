FROM node:20.18.0-bookworm-slim

# Create non-root runner user
RUN groupadd -g 1001 runner && \
    useradd -u 1001 -g runner -m -s /bin/bash runner

# Pre-install React, Vite, Vitest, and React Testing Library offline
WORKDIR /usr/local/lib/studio-react
RUN npm init -y && \
    npm install --no-audit --no-fund \
      react@18.3.1 \
      react-dom@18.3.1 \
      vite@5.4.11 \
      vitest@2.1.8 \
      @testing-library/react@16.0.1 \
      jsdom@25.0.1

ENV NODE_PATH="/usr/local/lib/studio-react/node_modules"

USER runner
WORKDIR /workspace

CMD ["npx", "vitest", "run"]
