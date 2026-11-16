     1	[server]
     2	host = "127.0.0.1"
     3	port = 8765
     4	transport = "streamable-http"
     5	
     6	[database]
     7	path = "~/.local/share/agent-memory/memory.db"
     8	journal_mode = "wal"
     9	busy_timeout_ms = 5000
    10	
    11	[embedding]
    12	# BGE-M3 runs as a local llama service container.
    13	# Use a host-reachable URL, e.g. http://host.docker.internal:8001 or the
    14	# container's exposed host port.
    15	provider = "bge-m3-http"
    16	endpoint = "http://127.0.0.1:8001"
    17	model = "bge-m3"
    18	dimension = 1024
    19	enabled = true
    20	
    21	[retrieval]
    22	lexical_top_k = 20
    23	vector_top_k = 20
    24	final_top_k = 6
    25	rrf_k = 60
    26	
    27	[memory]
    28	auto_capture = true
    29	approval_required_for_adr = true
    30	max_context_tokens = 2000
    31	
    32	[events]
    33	durable_spool = true
    34	retry_enabled = true
    35	max_extraction_attempts = 1
    36	
    37	[security]
    38	# Credentials and admin tokens should come from environment variables or the
    39	# macOS Keychain, not from this TOML file.
    40	mcp_allowed_agents = ["pi", "codex", "opencode"]
    41	admin_token_env = "AGENT_MEMORY_ADMIN_TOKEN"