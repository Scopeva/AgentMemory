1. [How to Give Your AI Agents Persistent Memory with MCP](https://genaiunplugged.substack.com/p/give-your-ai-agents-memory-mcp-shared)
Persistent memory in an MCP agent workflow comes from adding three tools to your MCP server: save_memory, read_memory, and search_memory, backed ...

2. [Use Agent Memory with an MCP Server](/goto?url=CAESkwEBxCJF174_Vv8kNIKNsHQ-tv2LDj5GJnRWz1xQHLK0FveJcVS4tY3cMZhOhaW0wue2PqEFse9jxTiZmc0ylUTclTDcSzzvq61Ben1J--i_RzUSfVdZtmKn7q5JPjbuK5e33ihCCJisVxZ-WKwbQ0oWwwF_Km-lqWHMwl3UGBz-IYeZmbiY2hqKZxJ2jbJpU-GyOJg&gsessionid=Hv9yBZPKCN02RXyK40j-nPhXzQpm2t_0yVQddUV9ncCwYZpjuPdOUg)
In this article, you will expose Oracle AI Agent Memory as Model Context Protocol (MCP) tools so that compatible agent runtimes can access memory through an MCP ...

3. [Memory MCP Server (Knowledge Graph): Tools, Setup & ...](/goto?url=CAESWgHEIkXX5IY-h4x-_16mlS4WySJa6ih_OSICDbLl444Nv9NaOnMz4FIVHU0bZh5ykcU60ZmiEMqonHtb0LnPgQepMxEO9vcV89OW56OfiGL-DHad465MjLDueQ&gsessionid=Hv9yBZPKCN02RXyK40j-nPhXzQpm2t_0yVQddUV9ncCwYZpjuPdOUg)
Oct 16, 2026 — It tells the model to start each chat by retrieving its "memory", to watch for identity, behaviors, preferences, goals and relationships, and to ...

4. [FastMCP tools with Shared Memory for AI Agents](https://mem0.ai/blog/fastmcp-tools-with-shared-memory-for-ai-agents)
The Pattern: Memory Retrieval at Tool Entry, Memory Write on State Change. The core pattern has two parts. At the start of each tool invocation, retrieve any memories relevant to the user and the current task. At the end of the invocation, if the call produced new information worth keeping, write it to the memory store. A single Mem0 client instance is shared across all tool definitions in the server . Tool functions become stateful from the agent &#39;s perspective while the MCP protocol remains unchanged.

5. [— Open-Source Titen MCP Memory Server for AI Agents](https://titen.dev/mcp-memory-server)
An MCP gives compatible memory a standard server interface for durable agents . Titen runs one on this machine with nothing to configure, and serves the same tool over an authenticated HTTP endpoint when several memory one store. tools agents share What does an MCP do? memory lets an server host discover and call MCP through a standard JSON-RPC handshake. agent tools