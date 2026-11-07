"""Skills taxonomy and skill extraction.

Each entry is written as  "Canonical|alias|alias"  - matching is case-insensitive
unless an alias is prefixed with "=", which makes it case-sensitive (used for
words like "Go", "React" or "Excel" that are also ordinary English words).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TAXONOMY: dict[str, list[str]] = {
    "Languages": [
        "Python", "Java", "JavaScript|js|ecmascript", "TypeScript", "C++|cpp", "C#|csharp|c sharp",
        "=Go|golang", "Rust", "Ruby", "PHP", "Swift", "Kotlin", "Scala", "=R", "MATLAB", "Perl", "Dart",
        "Bash|shell scripting|bash scripting", "PowerShell", "SQL", "HTML|html5", "CSS|css3", "Sass|scss",
        "Haskell", "Elixir", "Lua", "Objective-C", "Solidity", "Julia", "VBA", "COBOL", "Groovy", "Clojure",
        "F#",
    ],
    "Frontend": [
        "=React|react.js|reactjs", "Angular|angularjs", "Vue.js|vue|vuejs", "Next.js|nextjs", "Nuxt|nuxt.js",
        "Svelte", "Redux", "jQuery", "Tailwind CSS|tailwind|tailwindcss", "Bootstrap", "Webpack", "Vite",
        "Material UI|mui", "Three.js", "D3.js|d3", "Storybook", "Responsive Design|responsive web design",
        "Accessibility|a11y|wcag", "Web Performance|core web vitals",
    ],
    "Backend": [
        "Node.js|node|nodejs", "=Express|express.js|expressjs", "Django", "Flask", "FastAPI",
        "Spring Boot|springboot", "=Spring|spring framework", "Ruby on Rails|rails", "Laravel",
        "ASP.NET|asp.net core", ".NET|dotnet|.net core", "GraphQL", "=REST|rest api|rest apis|restful|restful apis",
        "gRPC", "Microservices|microservice|microservice architecture", "NestJS", "Celery", "RabbitMQ",
        "Kafka|apache kafka", "WebSockets|websocket", "API Design|api development", "Distributed Systems",
        "Event-Driven Architecture|event driven architecture|event-driven", "Message Queues|message queue",
        "Caching",
    ],
    "Databases": [
        "PostgreSQL|postgres", "MySQL", "SQLite", "MongoDB|mongo", "Redis", "Elasticsearch|elastic search",
        "Cassandra", "DynamoDB", "Oracle Database|oracle db", "SQL Server|mssql|microsoft sql server",
        "Firebase", "Supabase", "Snowflake", "BigQuery", "Redshift", "Neo4j", "MariaDB", "NoSQL",
        "Database Design|schema design", "Pinecone", "Vector Databases|vector database|vector db",
    ],
    "Cloud & DevOps": [
        "AWS|amazon web services", "Azure|microsoft azure", "GCP|google cloud|google cloud platform",
        "Docker", "Kubernetes|k8s", "Terraform", "Ansible", "Jenkins", "GitHub Actions", "GitLab CI|gitlab ci/cd",
        "CI/CD|ci-cd|ci cd|continuous integration|continuous delivery|continuous deployment", "Linux", "Unix",
        "Nginx", "Helm", "Prometheus", "Grafana", "Serverless", "AWS Lambda|lambda functions", "EC2", "S3",
        "CloudFormation", "Heroku", "Vercel", "Netlify", "Datadog", "Splunk", "OpenShift", "Argo CD|argocd",
        "Infrastructure as Code|iac", "Observability", "Monitoring", "DevOps", "SRE|site reliability engineering",
        "Networking|tcp/ip",
    ],
    "Data & AI": [
        "Machine Learning|=ML", "Deep Learning", "NLP|natural language processing", "Computer Vision",
        "TensorFlow", "PyTorch", "scikit-learn|sklearn|scikit learn", "Keras", "Pandas", "NumPy", "SciPy",
        "Matplotlib", "Seaborn", "Plotly", "Jupyter|jupyter notebooks", "Spark|apache spark|pyspark", "Hadoop",
        "Airflow|apache airflow", "dbt", "ETL|elt|data pipelines|data pipeline", "Data Analysis|data analytics",
        "Data Visualization|data visualisation", "Statistics|statistical analysis|statistical modeling",
        "A/B Testing|ab testing|a/b tests|experimentation", "Tableau", "Power BI|powerbi",
        "=Excel|microsoft excel|ms excel|advanced excel", "LLMs|=LLM|large language models|large language model",
        "Generative AI|genai|gen ai", "Prompt Engineering", "LangChain", "Hugging Face|huggingface", "OpenCV",
        "XGBoost", "MLOps", "Data Modeling|data modelling", "Data Warehousing|data warehouse", "Feature Engineering",
        "RAG|retrieval augmented generation|retrieval-augmented generation", "Time Series|time-series",
        "Big Data", "Data Engineering", "Data Science",
    ],
    "Mobile": [
        "Android", "iOS", "React Native", "Flutter", "SwiftUI", "Xcode", "Jetpack Compose",
        "Mobile Development|mobile app development",
    ],
    "Tools": [
        "Git", "GitHub", "GitLab", "Bitbucket", "Jira", "Confluence", "Postman", "Figma", "Selenium", "Cypress",
        "Jest", "Pytest", "JUnit", "Mocha", "Playwright", "npm", "Yarn", "Maven", "Gradle", "Sentry", "SonarQube",
        "Version Control",
    ],
    "Engineering practices": [
        "Unit Testing|unit tests|unit test", "Integration Testing|integration tests", "Test Automation|automated testing|automation testing",
        "TDD|test-driven development|test driven development", "Agile", "Scrum", "Kanban",
        "Code Review|code reviews", "System Design|systems design", "OOP|object-oriented programming|object oriented programming|object-oriented",
        "Design Patterns", "Data Structures", "Algorithms", "Debugging", "Performance Optimization|performance tuning",
        "Security|application security|appsec", "Cybersecurity|cyber security", "OWASP", "OAuth|oauth2",
        "JWT", "Authentication|authorization", "UI/UX|ui ux|user experience|ux design|ui design", "SEO",
        "Technical Documentation|documentation", "Scalability|scalable systems|scalable services",
    ],
    "Business & product": [
        "Product Management", "Project Management", "Stakeholder Management", "Roadmapping|product roadmap|roadmaps",
        "Requirements Gathering", "Business Analysis", "Market Research", "CRM", "Salesforce", "HubSpot",
        "Google Analytics", "Digital Marketing", "Content Marketing", "Copywriting", "Budgeting", "Forecasting",
        "Financial Modeling|financial modelling", "Negotiation", "Customer Success",
        "KPIs|=KPI|key performance indicators", "Data-Driven Decision Making|data-driven",
    ],
    "Soft skills": [
        "Communication|communication skills|communicator", "Leadership|leading teams|team leadership",
        "Teamwork|team player", "Collaboration|collaborate|collaborative|collaborated",
        "Problem Solving|problem-solving|problem solver", "Critical Thinking|analytical thinking",
        "Mentoring|mentored|mentorship|mentor", "Time Management", "Adaptability|adaptable",
        "Attention to Detail", "Public Speaking|presentation skills|presentations",
        "Cross-functional|cross functional", "Stakeholder Communication",
    ],
}

SOFT_CATEGORY = "Soft skills"

# Partial credit: if the job wants the key skill and the resume shows one of the
# related skills, it counts as a half match ("Pytest" is evidence of "Test Automation").
RELATED: dict[str, tuple[str, ...]] = {
    "Test Automation": ("Unit Testing", "Integration Testing", "Pytest", "Jest", "JUnit", "Mocha", "Selenium", "Cypress", "Playwright", "TDD"),
    "Unit Testing": ("Pytest", "Jest", "JUnit", "Mocha", "TDD"),
    "Observability": ("Monitoring", "Prometheus", "Grafana", "Datadog", "Sentry", "Splunk"),
    "Monitoring": ("Observability", "Prometheus", "Grafana", "Datadog", "Sentry", "Splunk"),
    "CI/CD": ("GitHub Actions", "GitLab CI", "Jenkins", "Argo CD"),
    "Infrastructure as Code": ("Terraform", "CloudFormation", "Ansible"),
    "Machine Learning": ("scikit-learn", "TensorFlow", "PyTorch", "Keras", "XGBoost", "Deep Learning"),
    "Deep Learning": ("TensorFlow", "PyTorch", "Keras"),
    "SQL": ("PostgreSQL", "MySQL", "SQL Server", "SQLite", "Oracle Database", "MariaDB", "BigQuery", "Snowflake"),
    "NoSQL": ("MongoDB", "DynamoDB", "Cassandra", "Redis", "Firebase"),
    "Data Visualization": ("Tableau", "Power BI", "Matplotlib", "Plotly", "Seaborn", "D3.js"),
    "Version Control": ("Git", "GitHub", "GitLab", "Bitbucket"),
    "Git": ("GitHub", "GitLab", "Bitbucket"),
    "Caching": ("Redis",),
    "Message Queues": ("Kafka", "RabbitMQ", "Celery"),
    "Event-Driven Architecture": ("Kafka", "RabbitMQ"),
    "Microservices": ("Kubernetes", "gRPC"),
    "Kubernetes": ("OpenShift", "Helm"),
    "JavaScript": ("TypeScript",),
    "Statistics": ("A/B Testing",),
    "Leadership": ("Mentoring",),
    "Collaboration": ("Cross-functional", "Teamwork", "Code Review"),
    "DevOps": ("CI/CD", "Docker", "Kubernetes", "Terraform"),
    "Cloud": ("AWS", "Azure", "GCP"),
    "Data Engineering": ("ETL", "Airflow", "Spark", "dbt"),
    "API Design": ("REST", "GraphQL", "FastAPI"),
}


@dataclass(frozen=True)
class Skill:
    name: str
    category: str
    pattern: re.Pattern
    cs_pattern: re.Pattern | None

    @property
    def soft(self) -> bool:
        return self.category == SOFT_CATEGORY


def _boundary(alias: str) -> str:
    """Regex for an alias that must stand alone as a 'word' (C++, .NET and CI/CD included)."""
    escaped = re.escape(alias).replace(r"\ ", r"[\s\-]+")
    if len(alias) <= 2:  # very short tokens like "R" or "Go": stricter boundaries
        guard = r"(?!\s+(?:to|above|beyond|ahead|live|out|through|the|for|back|over|get)\b)"
        return rf"(?<![\w+#.&/\-']){escaped}(?![\w+#&/\-']|\.\w){guard}"
    return rf"(?<![\w+#.]){escaped}(?![\w+#]|\.\w)"


def _compile(entry: str, category: str) -> Skill:
    parts = entry.split("|")
    name = parts[0].lstrip("=")
    ci_aliases: list[str] = []
    cs_aliases: list[str] = []
    for part in parts:
        if part.startswith("="):
            cs_aliases.append(part[1:])
        else:
            ci_aliases.append(part)
    pattern = re.compile("|".join(_boundary(a) for a in ci_aliases), re.IGNORECASE) if ci_aliases else re.compile(r"(?!x)x")
    cs_pattern = re.compile("|".join(_boundary(a) for a in cs_aliases)) if cs_aliases else None
    return Skill(name=name, category=category, pattern=pattern, cs_pattern=cs_pattern)


SKILLS: tuple[Skill, ...] = tuple(_compile(entry, cat) for cat, entries in TAXONOMY.items() for entry in entries)
SKILLS_BY_NAME: dict[str, Skill] = {s.name: s for s in SKILLS}

# Lower-cased aliases, used to stop skills being double-counted as plain keywords.
ALL_ALIASES: frozenset[str] = frozenset(
    part.lstrip("=").lower() for entries in TAXONOMY.values() for entry in entries for part in entry.split("|")
)


def find_skills(text: str) -> dict[str, list[int]]:
    """Return {skill name: [match start offsets]} for every skill mentioned in `text`.

    When one match sits inside a longer match of another skill ("React" inside
    "React Native", "Spring" inside "Spring Boot") only the longer one counts.
    """
    spans: list[tuple[int, int, str]] = []
    for skill in SKILLS:
        for pattern in (skill.pattern, skill.cs_pattern):
            if pattern is None:
                continue
            spans.extend((m.start(), m.end(), skill.name) for m in pattern.finditer(text))

    found: dict[str, set[int]] = {}
    for start, end, name in spans:
        covered = any(
            other != name and s <= start and e >= end and (e - s) > (end - start) for s, e, other in spans
        )
        if not covered:
            found.setdefault(name, set()).add(start)
    return {name: sorted(positions) for name, positions in found.items()}
