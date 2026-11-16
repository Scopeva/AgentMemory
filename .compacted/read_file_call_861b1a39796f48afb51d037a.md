    30	
    31	
    32	def _invoke_helper(action: str, payload: dict) -> Optional[dict]:
    33	    """Call the Python helper for a given action.
    34	
    35	    Returns the parsed JSON result, or None if the helper failed.
    36	    """
    37	    cmd = [sys.executable, _HELPER, action, json.dumps(payload)]
    38	    env = os.environ.copy()
    39	    # Forward relevant env vars
    40	    for key in (
    41	        "AGENT_MEMORY_SERVER_URL",
    42	        "AGENT_MEMORY_SPOOL_ROOT",
    43	        "AGENT_MEMORY_PROJECT_ID",
    44	        "AGENT_MEMORY_WORKSPACE_ID",
    45	        "AGENT_MEMORY_TASK_ID",
    46	    ):
    47	        if key in env:
    48	            cmd_env_val = env[key]
    49	    try:
    50	        result = subprocess.run(
    51	            cmd,
    52	            capture_output=True,
    53	            text=True,
    54	            timeout=10,
    55	            env=env,
    56	        )
    57	        if result.returncode == 0:
    58	            out = result.stdout.strip()
    59	            if out:
    60	                return json.loads(out)