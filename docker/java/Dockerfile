FROM eclipse-temurin:21-jdk-jammy

# Create non-root runner user
RUN groupadd -g 1001 runner && \
    useradd -u 1001 -g runner -m -s /bin/bash runner

# Install Maven and pre-cache JUnit 5 standalone jar
RUN apt-get update && \
    apt-get install -y --no-install-recommends maven curl && \
    mkdir -p /opt/junit && \
    curl -fsSL https://repo1.maven.org/maven2/org/junit/platform/junit-platform-console-standalone/1.10.2/junit-platform-console-standalone-1.10.2.jar \
      -o /opt/junit/junit-platform-console-standalone.jar && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV CLASSPATH=".:/opt/junit/junit-platform-console-standalone.jar"

USER runner
WORKDIR /workspace

CMD ["java", "-ea", "Main"]
