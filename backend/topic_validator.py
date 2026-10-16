import re
from typing import Tuple

# Common coding, software engineering, and computer science terms
CODING_KEYWORDS = {
    # Languages
    "python", "java", "javascript", "typescript", "c++", "cpp", "c#", "csharp", "c", "golang", "go",
    "rust", "ruby", "php", "swift", "kotlin", "scala", "dart", "sql", "bash", "shell", "powershell",
    "r", "matlab", "perl", "haskell", "lua", "assembly", "html", "css", "xml", "json", "yaml",
    
    # Frameworks & Libraries
    "spring", "spring boot", "react", "angular", "vue", "next.js", "nextjs", "django", "fastapi",
    "flask", "express", "node", "nodejs", "expressjs", "laravel", "rails", "asp.net", "dotnet",
    "pytorch", "tensorflow", "keras", "pandas", "numpy", "scikit-learn", "hibernate", "jpa",
    "tailwindcss", "bootstrap", "flutter", "react native", "graphql", "grpc", "redux",
    
    # Core Computer Science & Coding Concepts
    "data structures", "algorithms", "array", "linked list", "stack", "queue", "binary tree",
    "graph", "hash table", "hashmap", "sorting", "searching", "recursion", "dynamic programming",
    "oop", "object-oriented", "polymorphism", "inheritance", "encapsulation", "abstraction",
    "design patterns", "solid principles", "concurrency", "multithreading", "async", "await",
    "promise", "coroutine", "goroutine", "thread", "process", "memory management", "garbage collection",
    "pointers", "references", "lambda", "streams", "functional programming", "closures", "generics",
    "exceptions", "error handling", "debugging", "profiling", "refactoring",
    
    # Systems & Architecture
    "database", "databases", "relational", "nosql", "postgresql", "mysql", "mongodb", "redis",
    "sqlite", "cassandra", "elasticsearch", "neo4j", "index", "indexing", "transactions", "acid",
    "rest", "api", "apis", "microservices", "distributed systems", "system design", "docker",
    "kubernetes", "k8s", "ci/cd", "git", "github", "gitlab", "kafka", "rabbitmq", "message queue",
    "authentication", "jwt", "oauth", "security", "cryptography", "encryption", "networking",
    "tcp/ip", "http", "https", "websocket", "socket", "dns", "load balancing", "caching",
    
    # Software Engineering Topics
    "unit test", "unit testing", "integration testing", "tdd", "bdd", "mocking", "clean code",
    "software engineering", "compiler", "interpreter", "operating system", "linux", "kernel",
    "shell scripting", "cloud computing", "aws", "azure", "gcp", "serverless", "devops",
    "syntax", "loops", "functions", "variables", "classes", "methods", "interfaces", "types"
}

# Explicit non-coding categories to instantly flag
NON_CODING_PATTERNS = [
    r"\b(marketing|finance|accounting|economics|business administration|management|sales)\b",
    r"\b(history|literature|philosophy|poetry|creative writing|sociology|psychology)\b",
    r"\b(cooking|baking|culinary|gardening|carpentry|fashion|interior design)\b",
    r"\b(biology|anatomy|medicine|pharmacology|geology|astrology)\b",
    r"\b(french grammar|spanish literature|german vocabulary)\b"
]


def is_coding_topic(topic: str, tech: str = "") -> Tuple[bool, str]:
    """
    Validates if a topic and tech stack are programming/coding related.
    Returns (True, "") if valid, or (False, friendly_error_message) if not.
    """
    combined = f"{topic.lower()} {tech.lower()}"
    
    # 1. Check explicit non-coding patterns
    for pattern in NON_CODING_PATTERNS:
        match = re.search(pattern, topic.lower())
        if match:
            # But ensure it's not a CS application like "algorithms for finance" or "bioinformatics"
            if not any(k in combined for k in ["algorithm", "code", "programming", "python", "data", "model", "sql"]):
                matched_word = match.group(1).title()
                return False, (
                    f"'{topic}' appears to be related to {matched_word}, which is outside our coding focus. "
                    f"Verified Course Material Studio is exclusively tailored for professors teaching "
                    f"programming languages, algorithms, software engineering, and computer science subjects."
                )

    # 2. Check for coding keywords or tech presence
    words = set(re.findall(r"\b[a-zA-Z0-9_\-\.\#\+]+\b", combined))
    
    # Check if any tech keyword is recognized
    has_coding_keyword = any(kw in combined for kw in CODING_KEYWORDS)
    if has_coding_keyword:
        return True, ""
    
    # Check if tech field itself indicates coding
    tech_clean = tech.lower().strip()
    if any(k in tech_clean for k in ["java", "python", "c++", "c#", "react", "node", "sql", "spring", "script", "code"]):
        return True, ""
    
    # Check typical programming buzzwords in the topic title
    programming_terms = ["code", "coding", "program", "programming", "dev", "developer", "software", "syntax", "api", "bug"]
    if any(term in words for term in programming_terms):
        return True, ""

    # If ambiguous and very generic (e.g. "French Literature 101" or "World War II")
    # Provide a friendly, polite rejection message guiding the professor
    return False, (
        f"'{topic}' does not appear to be a coding or computer science subject. "
        f"Verified Course Material Studio only generates executable, code-verified decks. "
        f"Please provide a coding topic (e.g., 'Java 21 Virtual Threads', 'Spring Boot REST APIs', "
        f"'Binary Search Trees in C++', 'React Hooks and State Management')."
    )
