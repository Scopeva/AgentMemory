12:def _utcnow() -> str:
16:async def register_project(db: Database, project: Project) -> Project:
28:async def get_project(db: Database, project_id: str) -> Optional[Project]:
47:async def list_projects(db: Database, status: Optional[str] = None) -> list[Project]:
69:async def register_repository(db: Database, repo: Repository) -> Repository:
87:async def get_repository_by_fingerprint(
108:async def register_workspace(db: Database, ws: Workspace) -> Workspace:
126:async def get_workspace_by_path(