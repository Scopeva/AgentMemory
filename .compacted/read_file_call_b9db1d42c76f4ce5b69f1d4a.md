     1	"""Task repository with optimistic locking."""
     2	
     3	from __future__ import annotations
     4	
     5	from datetime import datetime, timezone
     6	from typing import Optional
     7	
     8	from agent_memory.schemas import Task, TaskStatus
     9	from agent_memory.storage.database import Database
    10	
    11	
    12	class TaskConflictError(Exception):
    13	    """Raised when a task update conflicts with a newer revision."""
    14	
    15	
    16	def _utcnow() -> str:
    17	    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    18	
    19	
    20	async def create_task(db: Database, task: Task) -> Task:
    21	    now = _utcnow()
    22	    await db.connection().execute(
    23	        "INSERT INTO tasks (task_id, project_id, title, status, revision, owner_session_id, created_at, updated_at) "
    24	        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
    25	        (
    26	            task.task_id,
    27	            task.project_id,
    28	            task.title,
    29	            task.status.value,
    30	            task.revision,
    31	            task.owner_session_id,
    32	            now,
    33	            now,
    34	        ),
    35	    )
    36	    return task
    37	
    38	
    39	async def get_task(db: Database, task_id: str) -> Optional[Task]:
    40	    async with db.connection() as conn:
    41	        cursor = await conn.execute(
    42	            "SELECT task_id, project_id, title, status, revision, owner_session_id, created_at, updated_at "
    43	            "FROM tasks WHERE task_id = ?",
    44	            (task_id,),
    45	        )
    46	        row = await cursor.fetchone()
    47	        if not row:
    48	            return None
    49	        return Task(
    50	            task_id=row["task_id"],
    51	            project_id=row["project_id"],
    52	            title=row["title"],
    53	            status=TaskStatus(row["status"]),
    54	            revision=row["revision"],
    55	            owner_session_id=row["owner_session_id"],
    56	            created_at=row["created_at"],
    57	            updated_at=row["updated_at"],
    58	        )
    59	
    60	