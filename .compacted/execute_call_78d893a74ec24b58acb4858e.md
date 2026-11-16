<error>
exit_code=1
stderr:
Traceback (most recent call last):
  File "<string>", line 2, in <module>
    from agent_memory.main import create_app
  File "/mnt/workspace/src/agent_memory/main.py", line 13, in <module>
    from agent_memory.mcp.server import mcp as mcp_server, bind_database
  File "/mnt/workspace/src/agent_memory/mcp/server.py", line 7, in <module>
    from mcp.server.fastmcp import FastMCP
  File "/mnt/workspace/.venv/lib/python3.13/site-packages/mcp/server/fastmcp.py", line 16, in <module>
    raise ModuleNotFoundError(_MESSAGE, name=__name__)
ModuleNotFoundError: No module named 'mcp.server.fastmcp'. This is mcp 2.x, where FastMCP was renamed to MCPServer (from mcp.server.mcpserver import MCPServer) and other APIs changed; see the migration guide at https://py.sdk.modelcontextprotocol.io/v2/migration/#fastmcp-renamed-to-mcpserver or pin 'mcp<2' to keep running v1 code.
</error>