6:dependencies = [
7-    "fastapi>=0.115.0",
8-    "uvicorn[standard]>=0.30.0",
9-    "mcp>=1.0.0",
10-    "pydantic>=2.10.0",
11-    "pydantic-settings>=2.6.0",
12-    "aiosqlite>=0.20.0",
13-    "tomli>=2.0.0; python_version < '3.11'",
14-    "typer>=0.12.0",
15-]
16-
17:[project.optional-dependencies]
18-dev = [
19-    "pytest>=8.0.0",
20-    "pytest-asyncio>=0.24.0",
21-    "ruff>=0.8.0",
22-    "mypy>=1.13.0",
23-]
24-embedding = [
25-    "httpx>=0.27.0",
26-]
27-cli = [
28-    "typer>=0.12.0",
29-]
30-
31-[build-system]
32-requires = ["setuptools>=68", "wheel"]
33-build-backend = "setuptools.build_meta"
34-
35-[tool.setuptools.packages.find]
36-where = ["src"]
37-