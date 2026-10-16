FROM node:20.18.0-bookworm-slim

# Create non-root runner user
RUN groupadd -g 1001 runner && \
    useradd -u 1001 -g runner -m -s /bin/bash runner

# Pre-install Tailwind 3.4.17 CLI and PostCSS offline
WORKDIR /usr/local/lib/studio-tailwind
RUN npm init -y && \
    npm install --no-audit --no-fund tailwindcss@3.4.17 postcss@8.4.49 autoprefixer@10.4.20

ENV PATH="/usr/local/lib/studio-tailwind/node_modules/.bin:${PATH}"

USER runner
WORKDIR /workspace

CMD ["npx", "tailwindcss", "-i", "input.css", "-o", "output.css", "--minify"]
