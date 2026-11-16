"""Project resolution and identity service."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Optional

from agent_memory.schemas import Project, Repository, Workspace
from agent_memory.storage import repositories as repo


@dataclass
class ProjectResolutionResult:
    project: Optional[Project]
    repository: Optional[Repository]
    workspace: Optional[Workspace]
    status: str  # "resolved" | "unresolved" | "partial"
    reason: Optional[str] = None


def normalize_path(p: str) -> str:
    """Normalize a workspace path for canonical identity."""
    path = Path(p).expanduser().resolve()
    return str(path)


def fingerprint_git_root(
    remote_url: Optional[str], root_path: str
) -> tuple[str, str]:
    """Compute stable identity from Git remote + normalized root.

    Credentials in remote_url are stripped before hashing.
    """
    cleaned_remote = _strip_git_credentials(remote_url or "")
    raw = f"{cleaned_remote}|{normalize_path(root_path)}"
    return sha256(raw.encode("utf-8")).hexdigest(), cleaned_remote


def _strip_git_credentials(url: str) -> str:
    """Remove user:pass@ from git remote URLs."""
    if "@" in url and "://" not in url:
        # scp-like syntax: user@host:path — keep host, drop user
        parts = url.split("@", 1)
        return parts[1]
    # https/user:pass@host — keep host
    if "://" in url:
        head, tail = url.split("://", 1)
        if "@" in tail:
            tail = tail.split("@", 1)[1]
        return f"{head}://{tail}"
    return url


async def resolve_project_by_workspace(
    db,
    canonical_path: str,
) -> ProjectResolutionResult:
    """Resolve project identity from a workspace path."""
    ws = await repo.projects.get_workspace_by_path(db, normalize_path(canonical_path))
    if ws is None:
        return ProjectResolutionResult(
            project=None,
            repository=None,
            workspace=None,
            status="unresolved",
            reason=f"No registered workspace matches path {canonical_path}",
        )

    # Walk up: workspace -> repository -> project
    # (repository and project need to be fetched; for now return partial)
    return ProjectResolutionResult(
        project=None,  # caller fetches via repository.project_id
        repository=None,
        workspace=ws,
        status="partial",
        reason="Workspace found; repository/project lookup required",
    )


async def resolve_project_by_id(
    db,
    project_id: str,
) -> ProjectResolutionResult:
    """Resolve an explicitly provided project_id."""
    project = await repo.projects.get_project(db, project_id)
    if project is None:
        return ProjectResolutionResult(
            project=None,
            repository=None,
            workspace=None,
            status="unresolved",
            reason=f"Project {project_id} not found",
        )
    return ProjectResolutionResult(
        project=project,
        repository=None,
        workspace=None,
        status="resolved",
    )


async def register_new_project(
    db,
    *,
    name: str,
    project_id: Optional[str] = None,
) -> Project:
    """Explicitly register a new project. Requires user confirmation in production."""
    import uuid

    p = Project(name=name, project_id=project_id or str(uuid.uuid4()))
    await repo.projects.register_project(db, p)
    return p


async def register_repository(
    db,
    *,
    project_id: str,
    remote_url: str,
    root_path: str,
    repository_id: Optional[str] = None,
) -> Repository:
    """Register a repository identity under a project."""
    import uuid

    fp, cleaned = fingerprint_git_root(remote_url, root_path)
    r = Repository(
        repository_id=repository_id or str(uuid.uuid4()),
        project_id=project_id,
        remote_url_hash=sha256(cleaned.encode("utf-8")).hexdigest(),
        root_fingerprint=fp,
    )
    await repo.projects.register_repository(db, r)
    return r


async def register_workspace(
    db,
    *,
    repository_id: str,
    canonical_path: str,
    worktree_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> Workspace:
    """Register a workspace (worktree/directory) under a repository."""
    import uuid

    w = Workspace(
        workspace_id=workspace_id or str(uuid.uuid4()),
        repository_id=repository_id,
        canonical_path=normalize_path(canonical_path),
        worktree_id=worktree_id,
    )
    await repo.projects.register_workspace(db, w)
    return w
