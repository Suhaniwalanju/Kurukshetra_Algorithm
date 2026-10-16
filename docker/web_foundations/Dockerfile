FROM mcr.microsoft.com/playwright:v1.49.1-jammy

# Configure non-root user
USER pwuser
WORKDIR /workspace

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

CMD ["node", "runner.js"]
