Local Agent Memory & Handoff Service完整开发方案 v1.0 · 2026-11-16 · 可作为开发 Agent 的实施规格1. 项目定位与最终技术决策本项目建设一个本地部署、无桌面依赖、支持多项目与多 Agent 的长期记忆及任务交接系统。面向你当前的 Orca、Pi、Codex、OpenCode 和 cmux 工作环境，解决以下问题：新 Session 自动恢复项目背景及最近工作进度。不同 Agent 共享已确认的架构决策、技术经验和问题解决方案。一个 Agent 未完成的任务，可以由另一个 Agent 接手。Agent 正常结束、上下文压缩、异常中断后，尽可能恢复有效工作状态。自动提取有价值的长期记忆，不依赖 Agent 每次主动调用 MCP。复用现有 BGE-M3 实现跨中英文的语义检索。保持 Token 消耗可控，不增加独立的生成式 LLM 服务。1.1 已确定的技术栈层次技术决策MCP 服务端Python + FastMCP确定事件 APIFastAPI / ASGI确定数据库SQLite + WAL确定全文检索SQLite FTS5确定语义检索sqlite-vec确定Embedding本地 BGE-M3确定记忆提取 LLMPi / Codex / OpenCode 自身模型确定任务事件捕获Agent Hooks / Extensions / Plugins确定异步处理SQLite 持久化任务队列 + Worker确定部署macOS launchd 或 OrbStack Docker两种方式均支持管理接口CLI 优先确定Web UI暂不实现延后BGE-M3 的 Dense 输出为 1024 维，支持 8192 Token 的长文本输入及多语言检索。第一版只使用 Dense Embedding，暂不实现其 Sparse 和 Multi-vector 能力。BAAI/bge-m3 at main1.2 明确不开发的功能第一版不做完整 Agent 编排平台，不接管 Orca 或 cmux 的 Session 执行，不复制整个代码仓库，不存储完整聊天历史作为长期知识，也不增加 PostgreSQL、Redis、知识图谱或独立 LLM Provider。最重要的架构约束：Memory Server 不负责运行开发 Agent，也不负责修改代码。它只管理项目记忆、任务状态、历史证据与交接信息。代码事实仍以当前 Git 仓库为准。2. 整体系统架构系统使用两条相互独立的数据通道。MCP 通道由 Agent 调用，负责项目背景查询、历史记忆搜索、获取交接信息和主动提交结构化记忆。Hook/Event 通道由 Agent 适配器调用，负责执行生命周期采集、检查点、完成事件、失败补偿和持久化确认。两条通道最终进入同一个 Memory Core，使用相同的项目身份、版本控制和权限体系。3. 系统模块划分建议按以下 8 个模块开发。模块职责不负责project-registry项目、Workspace、Worktree 身份与映射Git 代码索引session-trackerAgent Session、Run 与 Task 生命周期启动 Agent 进程handoff-manager项目进度、任务交接及恢复自动执行待办knowledge-store长期知识、ADR、来源、历史版本代码规范生成event-collectorHook 事件接收、校验、持久化LLM 推理memory-processor处理候选记忆、去重、审批、状态变更独立调用生成式 LLMretrieval-engineFTS5、向量搜索、融合与排序代码图谱搜索operations配置、迁移、备份、恢复、诊断完整 Web 管理后台所有模块共享同一套应用服务层。FastMCP Tools 和 HTTP API 都调用服务层方法，不能各自直接实现不同的数据库写入逻辑。4. 项目、任务和 Session 身份模型这部分必须在编码前确定，因为后续所有记忆记录都依赖它。ProjectWorkspace / Worktree / Branch ContextTask（可以跨多个 Session）Session（属于特定 Agent）Run → Events → Checkpoint4.1 身份定义实体主键主要字段Projectproject_idname、status、created_atRepositoryrepository_idproject_id、remote_url_hash、root_fingerprintWorkspaceworkspace_idrepository_id、canonical_path、worktree_idTasktask_idproject_id、title、state、owner、revisionSessionsession_idagent_type、native_session_id、workspace_idRunrun_idsession_id、task_id、started_at、outcomeEventevent_idrun_id、type、sequence、timestampCheckpointcheckpoint_idrun_id、source_revision、summaryHandoffhandoff_idtask_id、source_run_id、revisionKnowledgememory_idproject_id、type、status、revision其中：同一个项目可以包含多个 Workspace 和 Git Worktree。同一个 Task 可以跨 Agent、跨 Session 接续。Session ID 必须经过 Agent 类型命名空间处理。Branch 名称只能作为上下文，不能单独用作稳定身份。Git HEAD SHA 必须保存，用于判断交接信息是否过时。新建项目必须有显式注册或用户确认，不能只根据相似目录名自动合并。4.2 项目识别算法推荐优先级：Agent 或 Gateway 显式提供的 project_id。已登记的 Workspace / Worktree 映射。Git common directory、规范化 Remote 地址及项目注册信息。无法确认则进入 unresolved 状态，允许只读诊断，禁止写入其他项目。路径要经过规范化处理；Git Remote 可能包含认证信息，存储前必须去除凭据。不能将工作目录内任意配置文件视为可信的项目授权声明。4.3 记忆可见范围建议定义四级 Scope：run：仅当前执行过程。task：同一逻辑任务的各个 Agent。project：同一项目的所有 Session。global：跨项目通用经验，需要明确授权。默认长期 Knowledge 使用 project，Handoff 使用 task，Checkpoint 使用 run 或 task。跨项目搜索只能搜索明确标记为 global 的知识，不能默认读取其他项目的私有内容。5. SQLite 数据库设计建议采用单数据库、单写入服务、多读连接的模式。第一版不需要多数据库实例。5.1 数据库表表名核心用途projects项目注册repositoriesGit 仓库身份workspacesWorktree 和工作目录sessionsAgent 会话tasks逻辑任务及状态runs每次 Agent 执行events不可变生命周期事件checkpoints任务执行检查点handoffs交接记录及历史版本knowledge长期记忆当前版本knowledge_revisions长期记忆历史版本knowledge_sources证据、Commit、来源引用memory_candidatesAgent 提交的候选记忆approvals用户审批记录jobs持久化后台任务outbox同事务创建的后续处理事件memory_chunks用于检索的文本分块memory_ftsFTS5 虚拟表memory_vectorssqlite-vec 虚拟表embedding_profiles模型和预处理版本agent_capabilities已验证的 Hook / 恢复能力schema_migrations数据库迁移版本不建议用一个万能的 memories 表保存所有信息。Handoff、事件和长期知识具有不同的生命周期及一致性要求。5.2 数据库初始化配置SQLPRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = FULL;对于低并发本地应用，第一版可采用 synchronous=FULL，优先考虑事务提交的持久性；之后再通过性能测试评估是否需要调整。需要注意：journal_mode=WAL 是数据库持久设置。foreign_keys 和 busy_timeout 应在每个新数据库连接中设置。SQLite 同一时间仍然只能有一个写事务。所有写事务应尽量短。不要在数据库事务内部等待 BGE-M3、LLM 或外部 HTTP 请求。5.3 核心任务表以下是建议的逻辑 Schema，具体 SQL 可以在实施时拆分成独立 Migration。SQL
CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN (
            'pending', 'active', 'blocked',
            'completed', 'cancelled'
        )),
    revision INTEGER NOT NULL DEFAULT 1,
    owner_session_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id)
        REFERENCES projects(project_id)
);

CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    task_id TEXT,
    session_id TEXT NOT NULL,
    status TEXT NOT NULL,
    head_sha_start TEXT,
    head_sha_end TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    FOREIGN KEY (task_id)
        REFERENCES tasks(task_id)
);

CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    sequence_no INTEGER,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (run_id, sequence_no),
    FOREIGN KEY (run_id)
        REFERENCES runs(run_id)
);

CREATE INDEX idx_events_run
ON events(run_id, created_at);
事件 ID 使用稳定的幂等键。重试同一个事件必须得到相同 ID。对于 sequence_no，应明确由适配器生成还是服务端分配，不能依赖不同机器的时间戳排序。5.4 长期知识表SQL
CREATE TABLE knowledge (
    memory_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    current_source_revision TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id)
        REFERENCES projects(project_id)
);

CREATE TABLE knowledge_revisions (
    memory_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    PRIMARY KEY (memory_id, revision),
    FOREIGN KEY (memory_id)
        REFERENCES knowledge(memory_id)
);
知识更新必须使用乐观锁，例如：SQLUPDATE knowledge
SET
    content = :content,
    revision = revision + 1,
    updated_at = :updated_at
WHERE memory_id = :memory_id
  AND revision = :expected_revision;更新影响 0 行时返回 VERSION_CONFLICT，要求调用方重新读取。当前版本更新、历史版本插入以及 Outbox 事件创建，应当在同一事务中完成。5.5 状态约束Knowledge 状态：candidate → accepted → superseded同时允许 rejected、archived 等终态。需要额外保存：evidence_status：证据是否已验证。approval_status：是否获得必要的用户审批。supersedes_memory_id：替代了哪条旧知识。source_revision：知识对应的代码版本或文档版本。不允许模型仅通过输出 verified: true 就把候选记忆标记为已验证。验证状态必须通过服务端证据检查或用户审批形成。6. MCP 工具契约第一版建议仅提供 9 个面向 Agent 的核心工具。工具输入重点输出resolve_projectworkspace / 显式 project_id项目身份、访问范围get_project_contextproject_id、context_budget精简项目背景search_memoryproject_id、query、filters、limit相关知识及引用get_memorymemory_id完整知识、版本、证据get_task_statetask_id / project_id任务进度get_latest_handofftask_id、workspace_id最近有效交接create_handofftask_id、summary、evidenceHandoff ID、版本submit_memory_candidateproject_id、memories、idempotency_key候选 ID、校验状态update_task_statetask_id、expected_revision、state新任务状态正式 Knowledge 的批准、删除和强制覆盖，不建议直接开放给普通开发 Agent。应通过独立管理 API 或 CLI 执行。6.1 get_project_context示例请求：JSON
{
  "project_id": "website-audit-core",
  "task_id": null,
  "include": [
    "project_summary",
    "active_tasks",
    "accepted_constraints",
    "recent_handoffs"
  ],
  "max_output_tokens": 2000
}
此工具不应该返回整个项目记忆库，而应按预算返回最重要信息。Token 预算由服务端使用确定的 Tokenizer 或保守估算控制；超出预算时截断并返回可继续查询的引用。6.2 submit_memory_candidateJSON
{
  "schema_version": "1.0",
  "project_id": "website-audit-core",
  "run_id": "run-example-001",
  "idempotency_key": "example-memory-001",
  "memories": [
    {
      "type": "problem_solution",
      "title": "Example issue resolution",
      "content": "A verified solution summary.",
      "scope": "project",
      "evidence": [
        {
          "kind": "git_commit",
          "value": "example-commit-sha"
        }
      ]
    }
  ]
}
服务端必须校验：Schema 版本及所有字段类型。Project / Run 是否存在并具有相应权限。内容长度、数量和敏感数据。是否与既有 Knowledge 重复。是否与已确认的架构决策冲突。证据引用能否验证。此接口只创建候选记忆，不允许绕过审核直接修改已接受的 ADR。6.3 统一 MCP 错误契约建议固定以下错误码：错误码含义PROJECT_UNRESOLVED无法确定项目身份PROJECT_ACCESS_DENIED项目访问被拒绝SESSION_NOT_FOUNDSession 不存在TASK_CONFLICTTask 状态冲突VERSION_CONFLICT记忆版本已变更INVALID_EVIDENCE证据格式或来源无效APPROVAL_REQUIRED需要人工审核MEMORY_DUPLICATE已存在高度重复知识EMBEDDING_UNAVAILABLE语义模型不可用INVALID_SCHEMA_VERSION客户端契约不兼容业务异常采用稳定的结构化错误数据；协议层异常仍遵循 MCP 的响应与错误规范。7. Hook 事件接口与可靠性设计Hook 不需要通过 MCP 提交生命周期事件。 建议独立使用 HTTP Event API，避免模型工具调用与自动事件混在一起。基础接口：纯文本POST /v1/events
POST /v1/events/batch
POST /v1/checkpoints
POST /v1/extractions
GET  /v1/runs/{run_id}
GET  /v1/jobs/{job_id}

GET  /health/live
GET  /health/ready管理 API 另设权限，例如：纯文本GET  /v1/admin/pending
POST /v1/admin/approvals/{id}/approve
POST /v1/admin/approvals/{id}/reject
POST /v1/admin/jobs/{id}/retry7.1 事件 EnvelopeJSON
{
  "schema_version": "1.0",
  "event_id": "evt-001",
  "event_type": "run.settled",
  "agent": "pi",
  "session_id": "pi-session-001",
  "run_id": "run-001",
  "project_id": "website-audit-core",
  "workspace_id": "workspace-001",
  "task_id": "task-001",
  "sequence_no": 12,
  "occurred_at": "2026-11-16T09:00:00Z",
  "payload": {
    "outcome": "completed",
    "extraction_status": "pending"
  }
}
服务端收到事件时：校验客户端身份、Schema、大小限制和项目访问范围。用事件 ID 去重。将事件持久化到 SQLite。在必要时同步创建后续处理 Job。事务提交后再响应成功。只有成功提交后，Hook 才能删除本地缓冲中的对应事件。7.2 Hook 本地 Spool为了避免 Memory Server 离线导致事件丢失，每个 Agent Adapter 应有一个轻量本地 Spool。建议目录：纯文本~/.local/state/agent-memory/
├── pi/
├── codex/
└── opencode/采用仅当前用户可访问的持久化文件，或者由共享 Adapter 库管理本地 SQLite Spool。一个事件的状态是：created → locally_persisted → delivered → acknowledged采用 at-least-once delivery，依赖服务端幂等去重，而不是尝试保证端到端严格 exactly-once。缓冲文件限制大小、数量和保留时间，超过阈值必须告警，不能静默丢弃。7.3 Agent 记忆提取状态机需要增加三个异常状态：extraction_failed、interrupted 和 recovery_required。如果 Agent 没有成功输出记忆，绝不能自动标记 committed。同时允许合法的空结果：JSON{
  "run_id": "run-001",
  "result": "no_durable_memory",
  "memories": []
}这表示已经完成记忆评估，但本次没有值得长期保存的信息。7.4 防止递归调用必须建立系统级规则：记忆提取引发的内部继续执行标记为 origin=memory_extraction。同一个 Run 最多允许一次常规提取补偿。内部提取过程不得再次触发新的提取任务。不能在 Hook 中无限循环请求 Agent 继续执行。失败超过限制后标记 recovery_required，由下一次受控恢复或人工处理。这一限制必须由 Adapter 和 Memory Server 双方共同执行，而不是只写在 AGENTS.md 中。8. 三个 Agent 的适配器设计三个 Agent 的生命周期能力不同，应分别实现 Adapter，但复用相同的事件 Schema、Spool、HTTP Client 和错误处理库。8.1 Pi Extension建议实现位置：adapters/pi/核心事件：Pi 事件建议行为session_start登记 Session，恢复未发送事件before_agent_start登记 Run，并按需提供精简项目上下文turn_end维护事件序号和轻量进度agent_before_settle仅在符合条件时请求一次记忆提取继续执行agent_settled发送最终 Run 状态及结果引用session_before_compact保存可恢复检查点session_shutdown刷新 Spool，执行资源清理Pi 官方生命周期定义明确区分了 agent_end、agent_before_settle 和 agent_settled：最后一个表示自动重试和后续执行已结束；被中止的 Run 也可能跳过 agent_before_settle。因此不能只依赖结束前的提取事件。PiPi Adapter 应分为两个内部模块：SessionObserver 负责观察并保存事件，MemoryCaptureController 负责判断是否允许触发一次受控的 LLM 记忆提取。避免在事件回调中执行耗时的 Embedding 或数据库扫描。8.2 Codex Hook建议实现位置：adapters/codex/使用：SessionStart：建立身份与恢复状态。UserPromptSubmit：记录用户发起任务的边界。Stop：检查结束状态并尝试结构化记忆提取。PreCompact：保存检查点。Interrupt：标记中断。SessionEnd：最终清理及事件提交。Codex 官方 Hooks 文档已经包含 Stop、PreCompact、SessionStart、SessionEnd 等事件，也明确列出了自动生成持久记忆作为用途。ChatGPT Learn这里特别需要注意：Codex 的 SessionEnd 不应被视为每个任务完成时都会触发。官方说明该事件可能在会话关闭或满足一定空闲条件时才发生。实际记忆提取应该围绕 Stop / 回合完成设计，SessionEnd 只作为补充。ChatGPT Learn还需通过集成测试确认 Orca 使用的 Codex 启动方式是否加载全局 Hook，并且实际使用的是哪个 CODEX_HOME。8.3 OpenCode Plugin建议实现位置：adapters/opencode/核心关注：Session 创建和恢复。session.idle 等空闲边界。Session 压缩事件。执行错误与中断事件。完成任务后的结构化提取和状态同步。OpenCode 支持全局及项目级 Plugin，且可以从配置目录加载本地 JavaScript / TypeScript 插件。OpenCode不过，不能直接假设 OpenCode 的空闲事件允许像 Pi 一样请求一个最终继续执行。第一阶段应先实现只观察、不干预 Agent 的 Hook，再针对实际 Plugin API 测试是否能安全发起提取。8.4 统一能力协商为避免把三个 Agent 当成完全相同的运行时，建议适配器启动时向 Memory Server 注册能力。JSON
{
  "agent": "pi",
  "adapter_version": "1.0.0",
  "capabilities": {
    "session_lifecycle": true,
    "turn_completion": true,
    "pre_compaction": true,
    "controlled_continuation": true,
    "session_resume": true,
    "durable_spool": true
  }
}
这些值必须来自该 Adapter 的实际测试结果，而不是根据 Agent 名称硬编码。Memory Server 根据能力决定如何处理：能力情况策略支持受控继续执行尝试正常结束前完成记忆提取只能观察任务结束保存 Pending，等待可用的提取入口支持 Session 恢复后续可补提取不支持恢复保留证据和 Pending，不自动伪造知识这样未来增加 Orca 原生适配、其他 CLI Agent 或 Gateway Adapter 时，只需要实现能力契约。9. 自动记忆提取规范生成式 LLM 完全由原来的开发 Agent 提供，Memory Server 不配置额外的聊天模型。9.1 提取触发规则不是每个模型 Turn 都需要生成长期知识。建议分三类：任务结果处理普通问答、简单查询、无状态修改记录最小事件；可跳过 Handoff实际代码修改、Bug 修复、阶段任务生成精简 Handoff重要架构决策、长期约束、已验证问题解决方案生成 Handoff + Knowledge Candidate服务端可以先依据事件、Git 变更标记、任务标签等进行确定性的轻量分类，但无法仅靠规则准确判断技术意义。最终语义判断交给 Agent；无法判断时保留 Pending，而不是强制生成记忆。9.2 提取输出契约JSON
{
  "schema_version": "1.0",
  "run_id": "run-001",
  "capture_result": "captured",
  "handoff": {
    "summary": "Short task summary",
    "completed": [],
    "pending": [],
    "blockers": [],
    "next_actions": [],
    "head_sha": null
  },
  "memories": [
    {
      "type": "problem_solution",
      "title": "Short title",
      "content": "Reusable verified finding",
      "scope": "project",
      "evidence_refs": [],
      "proposed_status": "candidate"
    }
  ]
}
capture_result 使用枚举：captured、no_durable_memory、incomplete、failed。提取结果必须能通过严格 Schema 校验。格式错误时允许一次限定范围的修正，不要反复请求模型重做全部任务。9.3 证据分级等级证据是否允许直接成为 AcceptedE0Agent 自述，无外部证据否E1文件路径、历史日志或工具输出引用默认否E2可验证的 Git 变更、测试记录、当前源码可以进入自动验证流程E3用户正式审批或明确确认的决策允许按策略接受需要说明：E2 代表存在可验证证据，不意味着测试通过就能证明一项架构决策合理。重大 ADR、跨项目全局知识和核心技术约束仍需 E3 审批。10. BGE-M3、FTS5 与 sqlite-vec10.1 索引架构建议采用：Knowledge → Chunking → Outbox → BGE-M3 → sqlite-vec检索同时执行：FTS5 BM25 + Dense KNN → RRF → 权威性/时效性过滤 → 结果使用 sqlite-vec 的 vec0、分区键和元数据过滤能力，但需要锁定版本并运行兼容性测试。sqlite-vec 相关实现支持 KNN、partition key 和 metadata filter，具体组合需要由所锁定版本的集成测试确认。GitHub10.2 Embedding Provider 接口服务端只依赖一个抽象接口：Python运行from typing import Protocolclass EmbeddingProvider(Protocol):    async def embed(        self,        texts: list[str]    ) -> list[list[float]]:        ...    async def health(self) -> bool:        ...第一版实现 BgeM3HttpProvider。必须验证：输出向量维度是否为 1024。是否包含 NaN、Infinity 或空向量。输入长度限制和截断方式。批处理请求上限。响应超时和重试策略。模型版本、归一化规则及向量距离度量。你现有 BGE-M3 的具体 HTTP API 尚未明确，因此不要把 Ollama、OpenAI-compatible 或 FlagEmbedding 的某种请求格式写死到业务层。10.3 Chunking 策略项目记忆不同于普通长文档，建议：ADR：优先按 Context / Decision / Consequences 切分。Problem Solution：问题描述与解决方案尽量保持完整。Constraints：按独立约束条目切分。Handoff：默认不生成向量，或仅索引精简摘要。短于约定阈值的知识：整条作为一个 Chunk。初始 Chunk 建议约 300–700 Tokens，并保留少量上下文重叠；这属于待评估的工程参数，不是 BGE-M3 的硬性要求。10.4 Hybrid Search检索流程必须先确定项目访问范围，再搜索。按项目、记忆状态、Scope 过滤。FTS5 获取关键词 Top-K。sqlite-vec 获取该项目内的 Dense Top-K。使用 RRF 融合。对 superseded、archived 默认排除。返回内容摘要、来源和相关性信息。默认建议：FTS5 Top 20。Vector Top 20。RRF 常数 60。最终返回 Top 5–8。这些是初始化参数，需要通过测试集调整。10.5 降级与一致性Embedding 服务不可用时：主数据保存不能失败。Outbox 保留待索引任务。检索自动降级 FTS5。API 返回 retrieval_mode=lexical_only。恢复后自动补齐 Embedding。数据版本不匹配的索引必须重建。所有索引都必须能够从 Knowledge 主数据重新生成。索引不是权威存储。11. Handoff 交接协议Handoff 是系统的核心能力，应该有严格的数据契约。JSON
{
  "handoff_id": "handoff-001",
  "task_id": "task-001",
  "source": {
    "agent": "pi",
    "session_id": "session-001",
    "run_id": "run-001",
    "workspace_id": "workspace-001",
    "head_sha": "example-sha"
  },
  "state": "in_progress",
  "summary": "Task progress summary",
  "completed": [],
  "pending": [],
  "blockers": [],
  "decisions": [],
  "verification_refs": [],
  "next_actions": [],
  "revision": 1
}
11.1 Handoff 恢复规则接收 Agent 首先解析 Project、Workspace、Task。随后：获取最新有效 Handoff。检查源分支与当前工作区的 HEAD。判断相关提交是否已包含在当前分支中。读取相关决策与未完成事项。检查当前源码及测试，避免重复修改。接续 Task，并创建自己的 Run。如果 HEAD 不一致，不能简单拒绝所有交接。应判断差异是已经合并、分支前进，还是两个 Worktree 的独立实现。不能证明兼容时，标记 Handoff 为 stale 或 needs_revalidation。11.2 Task Lease采用可选 Task Lease 和 Fencing Token：同一任务可以被多个 Agent 查询。只有当前合法的执行者可以提交受保护的任务状态变更。租约到期后，旧执行者不能覆盖新状态。独立任务、不同 Worktree 不应受到不必要的全项目锁限制。第一版先实现冲突检测、租约过期及 Fencing Token 校验，不开发复杂的自动任务调度器。12. 安全、可靠性和故障恢复12.1 安全边界服务默认只监听 127.0.0.1。MCP、事件接收和管理操作需要分开授权：接口建议权限MCP 查询项目级读取MCP 提交候选记忆项目级写入候选Hook Event API指定 Agent / Session 的事件写入审批 API本机管理员备份恢复本机管理员建议采用服务端生成的客户端凭据、短期 Session 令牌或经过认证的本地通道，不要信任请求正文中的 project_id 就直接授予写入权限。另外：不执行知识内容中出现的命令或指令。限制事件正文大小。默认不采集完整对话及原始工具日志。敏感字段在写入前做确定性过滤，并结合必要的内容检查。凭据放在受保护的配置或 macOS Keychain 中。禁止通过 API 读取任意本地文件路径。全部审计记录都要保留操作者、来源和时间。HTTP 服务如果通过 OrbStack 暴露，必须明确宿主机和容器网络边界。12.2 数据恢复策略故障恢复行为Memory Server 进程崩溃SQLite 重启后恢复已提交事件Hook 请求失败本地 Spool 重试BGE-M3 停止保留 Outbox，FTS5 降级Agent 异常退出恢复最后有效 Checkpoint记忆提取失败保留 Pending，不伪造摘要重复事件唯一事件 ID 幂等并发更新冲突返回版本冲突，保留双方内容SQLite 损坏从经过验证的备份恢复服务器升级失败回滚应用与兼容数据库版本12.3 备份策略建议每天生成一次 SQLite 一致性备份，并保留多份历史版本。使用 SQLite Backup API 或 VACUUM INTO，不要在数据库仍有活跃 WAL 写入时只复制 .db 主文件。备份文件需包含：数据库与 Schema 版本。应用版本。备份时间。校验摘要。如事件 Spool 尚未清空，还需独立保留 Spool。每次关键数据库 Migration 前自动备份。备份能否使用必须通过恢复测试验证，而不仅是检查文件是否存在。12.4 服务启动依赖启动顺序：Config → Database → Migration Check → Integrity Check → Event Recovery → Background Worker → HTTP/MCP ReadyBGE-M3 不应成为启动 Memory Server 的硬依赖。即使 Embedding 服务离线，基础状态、任务查询、Handoff 和 FTS5 仍应正常工作。13. 建议的代码仓库结构采用 Python 核心服务，加三个独立 Agent Adapter。纯文本agent-memory/
├── README.md
├── pyproject.toml
├── uv.lock
├── compose.yaml
├── Dockerfile
├── .env.example
│
├── docs/
│   ├── architecture.md
│   ├── data-model.md
│   ├── event-contract.md
│   ├── mcp-contract.md
│   ├── memory-policy.md
│   ├── agent-adapters.md
│   ├── security.md
│   ├── deployment.md
│   └── recovery.md
│
├── src/agent_memory/
│   ├── main.py
│   ├── config.py
│   ├── api/
│   │   ├── app.py
│   │   ├── events.py
│   │   ├── checkpoints.py
│   │   └── admin.py
│   ├── mcp/
│   │   ├── server.py
│   │   └── tools/
│   ├── core/
│   │   ├── projects/
│   │   ├── sessions/
│   │   ├── tasks/
│   │   ├── handoffs/
│   │   ├── knowledge/
│   │   ├── events/
│   │   └── approvals/
│   ├── storage/
│   │   ├── database.py
│   │   ├── migrations/
│   │   ├── repositories/
│   │   └── transactions.py
│   ├── retrieval/
│   │   ├── chunker.py
│   │   ├── lexical.py
│   │   ├── vector.py
│   │   ├── hybrid.py
│   │   └── embedding.py
│   ├── workers/
│   │   ├── dispatcher.py
│   │   ├── indexing.py
│   │   └── recovery.py
│   └── security/
│       ├── auth.py
│       ├── redaction.py
│       └── authorization.py
│
├── adapters/
│   ├── shared/
│   │   ├── event-schema/
│   │   ├── http-client/
│   │   └── spool/
│   ├── pi/
│   ├── codex/
│   └── opencode/
│
├── cli/
│   └── memoryctl/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── retrieval/
│   ├── resilience/
│   └── e2e/
│
└── scripts/
    ├── install-hooks/
    ├── backup/
    └── restore/其中 adapters/shared 可以使用 TypeScript 或 Node.js，共享 Event Schema、Spool 和 HTTP Client。Codex 如果采用命令 Hook，也可以通过同一个 Adapter CLI 转发事件。这样三个客户端不必分别重复实现完整的重试与幂等逻辑。14. 开发阶段与执行任务以下顺序按依赖关系组织，不建议并行开发尚未固定契约的模块。Phase 0契约冻结与环境验证交付：架构文档、身份模型、Event Schema v1、MCP Tool Schema v1、状态机、权限策略。验证 FastMCP 与 FastAPI 挂载方式，BGE-M3 的实际 API、sqlite-vec 兼容性，以及三个 Agent 在 Orca 中的 Hook 加载行为。退出条件： 所有核心接口都有可执行 Schema 和契约测试；对尚未验证的 Agent Hook 能力不做承诺。Phase 1可靠存储与项目身份实现 SQLite、Migration、项目注册、Workspace/Worktree 解析、Session/Task/Run、事件幂等、版本控制、备份。退出条件： 重复事件不能重复写入，多个任务写入不会错配项目，重启后状态可恢复，备份可以成功还原。Phase 2MCP 与 Handoff 基础能力实现九个 MCP 工具、Handoff 版本管理、任务状态更新、知识候选管理、项目隔离和访问控制。退出条件： 两个模拟 Agent 能在不同 Session 中接续同一任务，且旧版本写入不会覆盖新状态。Phase 3Pi 自动记忆闭环实现 Pi Extension、通用 Event Client、本地 Spool、受控 LLM 记忆提取、结构校验、Pending 恢复、防递归。退出条件： 正常任务可自动提交 Handoff；Agent 未生成记忆时保留待处理状态；服务离线后事件能够补发。Phase 4Hybrid Retrieval接入现有 BGE-M3、FTS5、sqlite-vec、异步 Outbox、RRF、版本化索引和检索评估集。退出条件： 跨中英文知识能正确检索；Embedding 离线时 FTS5 仍能工作；索引能够完整重建。Phase 5Codex / OpenCode 适配复用通用 Adapter 库，完成 Codex Hooks 和 OpenCode Plugin，实现会话识别、事件采集、记忆提取与恢复。退出条件： 三个 Agent 可以在同一项目共享长期知识，并跨 Session 交接任务。Phase 6知识治理与上线实现审批、冲突检测、过时知识处理、CLI、监控、安装脚本、恢复演练和完整文档。退出条件： 长期记忆可审核、可追踪、可回滚，所有 P0 故障测试通过。开发任务依赖#chatgpt-mermaid-_r_4md_{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:16px;fill:rgb(237, 237, 237);}@keyframes edge-animation-frame{from{stroke-dashoffset:0;}}@keyframes dash{to{stroke-dashoffset:0;}}#chatgpt-mermaid-_r_4md_ .edge-animation-slow{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 50s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_4md_ .edge-animation-fast{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 20s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_4md_ .error-icon{fill:rgb(48, 48, 48);}#chatgpt-mermaid-_r_4md_ .error-text{fill:rgb(237, 237, 237);stroke:rgb(237, 237, 237);}#chatgpt-mermaid-_r_4md_ .edge-thickness-normal{stroke-width:1px;}#chatgpt-mermaid-_r_4md_ .edge-thickness-thick{stroke-width:3.5px;}#chatgpt-mermaid-_r_4md_ .edge-pattern-solid{stroke-dasharray:0;}#chatgpt-mermaid-_r_4md_ .edge-thickness-invisible{stroke-width:0;fill:none;}#chatgpt-mermaid-_r_4md_ .edge-pattern-dashed{stroke-dasharray:3;}#chatgpt-mermaid-_r_4md_ .edge-pattern-dotted{stroke-dasharray:2;}#chatgpt-mermaid-_r_4md_ .marker{fill:rgb(175, 175, 175);stroke:rgb(175, 175, 175);}#chatgpt-mermaid-_r_4md_ .marker.cross{stroke:rgb(175, 175, 175);}#chatgpt-mermaid-_r_4md_ svg{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:16px;}#chatgpt-mermaid-_r_4md_ p{margin:0;}#chatgpt-mermaid-_r_4md_ .label{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";color:rgb(237, 237, 237);}#chatgpt-mermaid-_r_4md_ .cluster-label text{fill:rgb(237, 237, 237);}#chatgpt-mermaid-_r_4md_ .cluster-label span{color:rgb(237, 237, 237);}#chatgpt-mermaid-_r_4md_ .cluster-label span p{background-color:transparent;}#chatgpt-mermaid-_r_4md_ .label text,#chatgpt-mermaid-_r_4md_ span{fill:rgb(237, 237, 237);color:rgb(237, 237, 237);}#chatgpt-mermaid-_r_4md_ .node rect,#chatgpt-mermaid-_r_4md_ .node circle,#chatgpt-mermaid-_r_4md_ .node ellipse,#chatgpt-mermaid-_r_4md_ .node polygon,#chatgpt-mermaid-_r_4md_ .node path{fill:rgb(19, 33, 54);stroke:rgb(31, 78, 148);stroke-width:1px;}#chatgpt-mermaid-_r_4md_ .rough-node .label text,#chatgpt-mermaid-_r_4md_ .node .label text,#chatgpt-mermaid-_r_4md_ .image-shape .label,#chatgpt-mermaid-_r_4md_ .icon-shape .label{text-anchor:middle;}#chatgpt-mermaid-_r_4md_ .node .katex path{fill:#000;stroke:#000;stroke-width:1px;}#chatgpt-mermaid-_r_4md_ .rough-node .label,#chatgpt-mermaid-_r_4md_ .node .label,#chatgpt-mermaid-_r_4md_ .image-shape .label,#chatgpt-mermaid-_r_4md_ .icon-shape .label{text-align:center;}#chatgpt-mermaid-_r_4md_ .node.clickable{cursor:pointer;}#chatgpt-mermaid-_r_4md_ .root .anchor path{fill:rgb(175, 175, 175)!important;stroke-width:0;stroke:rgb(175, 175, 175);}#chatgpt-mermaid-_r_4md_ .arrowheadPath{fill:rgb(175, 175, 175);}#chatgpt-mermaid-_r_4md_ .edgePath .path{stroke:rgb(175, 175, 175);stroke-width:1px;}#chatgpt-mermaid-_r_4md_ .flowchart-link{stroke:rgb(175, 175, 175);fill:none;}#chatgpt-mermaid-_r_4md_ .edgeLabel{background-color:rgb(14, 14, 14);text-align:center;}#chatgpt-mermaid-_r_4md_ .edgeLabel p{background-color:rgb(14, 14, 14);}#chatgpt-mermaid-_r_4md_ .edgeLabel rect{opacity:0.5;background-color:rgb(14, 14, 14);fill:rgb(14, 14, 14);}#chatgpt-mermaid-_r_4md_ .labelBkg{background-color:rgba(14, 14, 14, 0.5);}#chatgpt-mermaid-_r_4md_ .cluster rect{fill:rgb(48, 48, 48);stroke:rgba(255, 255, 255, 0.15);stroke-width:1px;}#chatgpt-mermaid-_r_4md_ .cluster text{fill:rgb(237, 237, 237);}#chatgpt-mermaid-_r_4md_ .cluster span{color:rgb(237, 237, 237);}#chatgpt-mermaid-_r_4md_ div.mermaidTooltip{position:absolute;text-align:center;max-width:200px;padding:2px;font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:12px;background:rgb(48, 48, 48);border:1px solid rgba(255, 255, 255, 0.15);border-radius:2px;pointer-events:none;z-index:100;}#chatgpt-mermaid-_r_4md_ .flowchartTitleText{text-anchor:middle;font-size:18px;fill:rgb(237, 237, 237);}#chatgpt-mermaid-_r_4md_ rect.text{fill:none;stroke-width:0;}#chatgpt-mermaid-_r_4md_ .icon-shape,#chatgpt-mermaid-_r_4md_ .image-shape{background-color:rgb(14, 14, 14);text-align:center;}#chatgpt-mermaid-_r_4md_ .icon-shape p,#chatgpt-mermaid-_r_4md_ .image-shape p{background-color:rgb(14, 14, 14);padding:2px;}#chatgpt-mermaid-_r_4md_ .icon-shape .label rect,#chatgpt-mermaid-_r_4md_ .image-shape .label rect{opacity:0.5;background-color:rgb(14, 14, 14);fill:rgb(14, 14, 14);}#chatgpt-mermaid-_r_4md_ .label-icon{display:inline-block;height:1em;overflow:visible;vertical-align:-0.125em;}#chatgpt-mermaid-_r_4md_ .node .label-icon path{fill:currentColor;stroke:revert;stroke-width:revert;}#chatgpt-mermaid-_r_4md_ .node .neo-node{stroke:rgb(31, 78, 148);}#chatgpt-mermaid-_r_4md_ [data-look="neo"].node rect,#chatgpt-mermaid-_r_4md_ [data-look="neo"].cluster rect,#chatgpt-mermaid-_r_4md_ [data-look="neo"].node polygon{stroke:url(#chatgpt-mermaid-_r_4md_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_4md_ [data-look="neo"].swimlane.cluster rect{filter:none;}#chatgpt-mermaid-_r_4md_ [data-look="neo"].node path{stroke:url(#chatgpt-mermaid-_r_4md_-gradient);stroke-width:1px;}#chatgpt-mermaid-_r_4md_ [data-look="neo"].node .outer-path{filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_4md_ [data-look="neo"].node .neo-line path{stroke:rgb(31, 78, 148);filter:none;}#chatgpt-mermaid-_r_4md_ [data-look="neo"].node circle{stroke:url(#chatgpt-mermaid-_r_4md_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_4md_ [data-look="neo"].node circle .state-start{fill:#000000;}#chatgpt-mermaid-_r_4md_ [data-look="neo"].icon-shape .icon{fill:url(#chatgpt-mermaid-_r_4md_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_4md_ [data-look="neo"].icon-shape .icon-neo path{stroke:url(#chatgpt-mermaid-_r_4md_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_4md_ .node text{font-size:14px;font-weight:600;letter-spacing:normal;fill:rgb(153, 206, 255);}#chatgpt-mermaid-_r_4md_ .edgeLabels text{font-size:13px;font-weight:600;letter-spacing:-0.08px;fill:rgb(153, 206, 255);}#chatgpt-mermaid-_r_4md_ .node tspan[font-weight="normal"],#chatgpt-mermaid-_r_4md_ .edgeLabels tspan[font-weight="normal"]{font-weight:600;}#chatgpt-mermaid-_r_4md_ .edgeLabel .label rect{opacity:1;rx:13px;ry:13px;fill:rgb(0, 14, 26);stroke:rgb(26, 62, 95);stroke-width:1px;}#chatgpt-mermaid-_r_4md_ .node rect,#chatgpt-mermaid-_r_4md_ .node circle,#chatgpt-mermaid-_r_4md_ .node ellipse,#chatgpt-mermaid-_r_4md_ .node polygon,#chatgpt-mermaid-_r_4md_ .node path{fill:rgb(0, 40, 77);stroke:rgba(255, 255, 255, 0.1);stroke-width:1px;}#chatgpt-mermaid-_r_4md_ .node rect{rx:16px;ry:16px;}#chatgpt-mermaid-_r_4md_ .mermaid-decision .label-container{fill:rgb(0, 14, 26);stroke:rgb(26, 62, 95);stroke-dasharray:2,2;}#chatgpt-mermaid-_r_4md_ .edgePaths .flowchart-link{stroke:rgb(175, 175, 175);stroke-width:1px;stroke-linecap:round;stroke-linejoin:round;}#chatgpt-mermaid-_r_4md_ .marker{fill:rgb(175, 175, 175);stroke:rgb(175, 175, 175);}#chatgpt-mermaid-_r_4md_ :root{--mermaid-font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";}Phase 0ContractsPhase 1Storage & IdentityPhase 2MCP & HandoffPhase 3Pi AdapterPhase 4Hybrid RetrievalPhase 5Codex & OpenCodePhase 6Release HardeningPhase 3 和 Phase 4 可以在完成 Phase 2 契约后并行推进，因为一个主要涉及 Agent 生命周期，一个主要涉及索引与检索。15. 测试与验收标准需要建立可重复执行的自动化测试，不能只通过“Agent 看起来已经记住了”判断成功。15.1 核心测试矩阵测试项验收标准项目识别不同 Git Worktree 能映射正确项目项目隔离未授权 Agent 不能读取其他项目记忆Session 恢复新 Session 可以获得相应 Handoff跨 Agent 交接Pi → Codex → OpenCode 接续同一 Task事件幂等同一事件重复提交不会产生重复记录版本冲突并发修改不发生静默覆盖服务重启已确认保存的事件不丢失服务离线Spool 缓冲后可补发Agent 中断恢复最后有效 Checkpoint，状态不伪造提取防递归内部记忆提取不会无限触发 HookBGE-M3 离线主数据可保存，FTS5 正常索引恢复可以从 Knowledge 重建向量索引审批未授权的重要 ADR 不能直接发布备份恢复恢复后数据、版本及来源引用一致15.2 检索质量测试建议构建至少 50 个真实项目问题的测试集，覆盖：精确函数名、错误码、配置项。中文问题检索英文架构知识。历史 Bug 解决方案。已废弃 ADR 与当前 ADR 的区分。跨项目相似术语的隔离。当前分支与 Handoff 不匹配的情况。初期目标指标建议如下，均为工程验收目标而非现成性能保证：指标初始目标项目隔离错误0重复事件导致的重复记录0已确认事务在正常进程重启后丢失0Top-5 相关知识召回率≥ 85%默认上下文预算≤ 2,000 TokensBGE-M3 离线降级必须成功备份恢复测试必须通过对召回率的定义应固定为 Recall@5，使用人工标注的相关文档集评估。不能仅靠模型自评。15.3 安全测试必须包括：MCP 越权访问。伪造 Project ID。伪造 Session ID。向知识内容嵌入恶意指令。Hook 日志中的密钥泄漏。请求体过大。重放旧事件。非法路径读取。损坏的 Migration 与回滚。不可信仓库尝试修改全局 Agent Hook 配置。16. 部署设计考虑到你使用 macOS 和 OrbStack，第一版建议优先选择本机后台部署。16.1 原生 macOS 后台部署优势：直接访问现有 BGE-M3 本地接口。不需要处理容器与宿主机的 127.0.0.1 差异。便于管理 Agent Hook、本地 Spool 和 Session 文件。资源占用更低。建议通过 launchd 运行服务，并配置进程异常退出后的自动重启。16.2 Docker / OrbStack 部署也应支持 Docker，但要注意：容器里的 127.0.0.1 指向容器自身，而不是 macOS 宿主机。BGE-M3 的 API 地址必须通过显式可达的宿主机地址配置，不能直接照搬本机进程的 URL。SQLite 数据目录使用持久化卷，并要求底层文件系统正确支持 SQLite 文件锁。避免把活跃数据库放在不可靠的网络挂载目录。Docker 服务同样默认仅向宿主机回环地址发布端口。16.3 基础配置示例toml
[server]
host = "127.0.0.1"
port = 8765
transport = "streamable-http"

[database]
path = "~/.local/share/agent-memory/memory.db"
journal_mode = "wal"
busy_timeout_ms = 5000

[embedding]
provider = "bge-m3-http"
endpoint = "http://127.0.0.1:8001"
model = "bge-m3"
dimension = 1024
enabled = true

[retrieval]
lexical_top_k = 20
vector_top_k = 20
final_top_k = 6
rrf_k = 60

[memory]
auto_capture = true
approval_required_for_adr = true
max_context_tokens = 2000

[events]
durable_spool = true
retry_enabled = true
max_extraction_attempts = 1
这是项目自身的拟定配置格式，不是 FastMCP 内置配置文件。实际部署时，密钥不能放在这个 TOML 中。配置项还需要支持环境变量覆盖和 Schema 验证。17. CLI 与运维能力第一版不开发 Web UI，但建议实现一个 memoryctl CLI。Bashmemoryctl doctor
memoryctl status

memoryctl projects list
memoryctl projects register

memoryctl sessions list
memoryctl tasks list
memoryctl handoffs latest

memoryctl memory search
memoryctl memory inspect

memoryctl pending list
memoryctl approvals list
memoryctl jobs retry

memoryctl index status
memoryctl index rebuild

memoryctl backup create
memoryctl backup verify
memoryctl restore这些是需要开发的接口，并非已经存在的工具命令。doctor 必须检查 MCP 可用性、SQLite 数据库完整性、Schema 版本、BGE-M3 连接、索引状态、Spool、三个 Agent 的 Hook 加载状态和最近备份。其中 restore、强制重建索引、删除记录等操作必须具有明确的确认流程。18. 对现有 AGENTS.md 的集成你前面已经将 Obsidian 相关内容从三个 Agent 共用的 AGENTS.md 中移除。这个方案开发完成后，不需要重新引入大量复杂的 Memory Rules。建议只增加一段简短的职责说明：Markdown
## Project Memory

The shared Project Memory Server provides
cross-session project history and handoffs.

### Responsibilities

- Use project memory for historical context.
- Use Codebase-Memory for code structure.
- Treat current source code as authoritative.
- Validate historical claims against current code.
- Never store secrets in project memory.
- Do not manually simulate lifecycle events.
- Automatic memory capture is handled by
  installed Agent adapters and hooks.

### On Task Start

Retrieve relevant project context only
when needed.

### During Work

Search historical decisions and known solutions
when relevant.

### On Completion

Do not duplicate automatic memory capture.
The Agent adapter handles event persistence
and memory extraction checkpoints.
重点是避免双重记忆写入。Agent Adapter 的自动捕获与 MCP 的主动提交必须共享幂等和去重逻辑，不能把同一次工作分别保存成多条完全相同的知识。19. 最终交付清单开发验收清单用于执行过程中逐项检查0/20核心架构项目、Workspace、Session、Task、Run 数据模型Event / MCP / Handoff Schema v1FastMCP + FastAPI 单服务SQLite Migration 与数据版本控制记忆与可靠性Handoff 和 Knowledge 独立存储Hook 本地持久化 Spool事件幂等、重试与中断恢复证据校验、候选记忆与审批检索能力FTS5 全文检索本地 BGE-M3 复用sqlite-vec 语义检索Hybrid RRF 与异步索引恢复Agent 适配Pi ExtensionCodex HooksOpenCode PluginOrca 启动方式兼容验证工程交付CLI、诊断、备份与恢复单元、集成、契约和故障测试macOS launchd / Docker 部署AGENTS.md 更新与用户文档 复制验收进度20. 交付给开发 Agent 的执行原则建议在正式编码前，把以下规则作为项目级开发约束：先契约，后实现：Phase 0 必须确定 Schema、状态机、错误语义和模块边界。可靠性优先于智能化：先保证事件能保存、恢复、去重，再做自动记忆提取。不引入独立生成式 LLM：记忆提取只使用现有 Agent 的模型能力。不破坏现有 Codebase-Memory：它继续负责代码结构发现。不复制 Agent 编排能力：Memory Server 不代替 Orca、cmux 或 Gateway。主数据与索引分离：BGE-M3 故障不能阻止 SQLite 保存长期知识。保持最小权限：Agent 只访问授权项目，重要 ADR 必须审批。逐阶段验证：每一阶段通过测试后才能进入下一阶段；禁止跳过失败项后宣称完成。最终架构决策摘要Local Agent Memory & Handoff Service v1.0核心服务FastMCP + FastAPI主数据SQLite + WAL知识检索FTS5 + sqlite-vec + BGE-M3LLM 推理现有 Agent 自身模型自动化Hooks + Durable Event + Recovery项目隔离Project / Workspace / Task / Session长期记忆Evidence + Version + Approval交接恢复Handoff + Checkpoint + Git Context部署方式本机常驻 / OrbStack Docker建议将这份方案作为 v1.0 开发基线，先执行 Phase 0 的契约冻结和 Agent Hook 能力验证，再开始编写 SQLite 数据层。这样开发过程中不需要反复调整任务、Session、记忆和事件之间的关系，也不会因为后期增加 Codex 或 OpenCode 而重构整个系统。