/**
 * agent-memory plugin for OpenCode.
 *
 * Drop this file into ~/.config/opencode/plugin/agent-memory.ts (global)
 * or <project>/.opencode/plugin/agent-memory.ts (project-local).
 * OpenCode loads it automatically at startup — no separate install step.
 *
 * How it works:
 * - On chat.message we record the session + turn boundaries.
 * - On session lifecycle events we persist via the shared Python adapter
 *   by shelling out to a tiny bridge script (plugins/opencode/opencode_bridge.py).
 *
 * Env vars (read by the adapter on the Python side):
 *   AGENT_MEMORY_REPO_ROOT   path to the repo (required so the bridge can import adapters)
 *   AGENT_MEMORY_SERVER_URL  default http://127.0.0.1:8765
 *   AGENT_MEMORY_PROJECT_ID
 *   AGENT_MEMORY_WORKSPACE_ID
 *   AGENT_MEMORY_TASK_ID
 */
import { execFileSync } from "node:child_process";
import * as os from "node:os";
import * as path from "node:path";

const REPO_ROOT =
  process.env.AGENT_MEMORY_REPO_ROOT ??
  path.join(os.homedir(), "AgentMemory");

const BRIDGE = path.join(REPO_ROOT, "plugins", "opencode", "opencode_bridge.py");

function invoke(action: string, payload: Record<string, unknown>): void {
  try {
    execFileSync("python3", [BRIDGE, action, JSON.stringify(payload)], {
      stdio: "pipe",
      timeout: 5000,
    });
  } catch (err) {
    // Never block OpenCode on a bridge failure.
    // eslint-disable-next-line no-console
    console.error("[agent-memory] bridge call failed:", (err as Error).message);
  }
}

export default function agentMemoryPlugin() {
  let sessionStarted = false;

  return {
    events: {
      async "session.start"(ctx: { sessionID: string; reason?: string }) {
        sessionStarted = true;
        invoke("session_start", {
          session_id: ctx.sessionID,
          native_session_id: ctx.reason ?? "",
        });
      },

      async "chat.message"(ctx: {
        sessionID: string;
        messageID: string;
        info: { role: string };
      }) {
        if (!sessionStarted) return;
        // Every assistant turn is a "turn.end" from the memory model's view.
        invoke("turn_end", {
          session_id: ctx.sessionID,
          run_id: ctx.sessionID,
          turn_index: 0,
        });
      },

      async "session.end"(ctx: { sessionID: string; reason?: string }) {
        invoke("session_end", {
          session_id: ctx.sessionID,
          outcome: reasonToOutcome(ctx.reason),
        });
        sessionStarted = false;
      },
    },
  };
}

function reasonToOutcome(reason?: string): string {
  switch (reason) {
    case "completed":
      return "completed";
    case "error":
    case "failed":
      return "failed";
    case "cancelled":
    case "interrupted":
      return "interrupted";
    default:
      return "completed";
  }
}
