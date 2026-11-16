54:    lexical_top_k: int = 20
55:    vector_top_k: int = 20
56:    final_top_k: int = 6
57:    rrf_k: int = 60
---SCHEMAS---
239:class Knowledge(SchemaModel):
240-    memory_id: str = Field(default_factory=_new_uuid)
241-    project_id: str
242-    scope: KnowledgeScope = KnowledgeScope.PROJECT
243-    type: str  # e.g. "adr", "problem_solution", "constraint"
244-    status: KnowledgeStatus = KnowledgeStatus.CANDIDATE
245-    title: str
246-    content: str
247-    revision: int = 1
248-    current_source_revision: Optional[str] = None
249-    evidence: list[EvidenceRef] = Field(default_factory=list)
250-    supersedes_memory_id: Optional[str] = None
251-    created_at: str = Field(default_factory=_utcnow)
252-    updated_at: str = Field(default_factory=_utcnow)
253-
254-
255-class MemoryCandidate(SchemaModel):
256-    """Payload submitted by an agent via MCP submit_memory_candidate."""
257-
258-    project_id: str
259-    run_id: Optional[str] = None
---KNOW-LIST---
188:async def list_knowledge_by_project(
189-    db: Database,
190-    project_id: str,
191-    status: Optional[KnowledgeStatus] = None,
192-    scope: Optional[KnowledgeScope] = None,
193-    limit: int = 50,
194-) -> list[Knowledge]:
195-    sql = (
196-        "SELECT memory_id, project_id, scope, type, status, title, content, "
197-        "revision, current_source_revision, supersedes_memory_id, created_at, updated_at "
198-        "FROM knowledge WHERE project_id = ?"
199-    )
200-    params: list = [project_id]
201-    if status:
202-        sql += " AND status = ?"
203-        params.append(status.value)
204-    if scope:
205-        sql += " AND scope = ?"
206-        params.append(scope.value)
207-    sql += " ORDER BY updated_at DESC LIMIT ?"
208-    params.append(limit)
209-    async with db.connection() as conn:
210-        cursor = await conn.execute(sql, params)
211-        rows = await cursor.fetchall()
212-        return [
213-            Knowledge(
214-                memory_id=r["memory_id"],
215-                project_id=r["project_id"],
216-                scope=KnowledgeScope(r["scope"]),
217-                type=r["type"],
218-                status=KnowledgeStatus(r["status"]),
219-                title=r["title"],
220-                content=r["content"],
221-                revision=r["revision"],
222-                current_source_revision=r["current_source_revision"],
223-                supersedes_memory_id=r["supersedes_memory_id"],
224-                created_at=r["created_at"],
225-                updated_at=r["updated_at"],
226-            )
227-            for r in rows
228-        ]