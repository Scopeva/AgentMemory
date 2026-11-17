/**
 * agent-memory plugin for OpenCode.
 *
 * Drop this file into ~/.config/opencode/plugin/agent-memory.ts (global)
 * or <project>/.opencode/plugin/agent-memory.ts (project-local).
 * OpenCode loads it automatically at startup — no separate install step.
 *
 * How it works (batch bridge, #9):
 * - One long-lived Python bridge process is spawned on first use.
 * - Every OpenCode event is piped to its stdin as a single JSON line;
 *   the bridge persists + flushes internally, so we no longer fork a
 *   new Python interpreter per assistant message (~0.23 s/call before).
 * - The bridge is closed on session end / plugin unload.
 *
 * Env vars (read by the adapter on the Python side):
 *   AGENT_MEMORY_REPO_ROOT   path to the repo (so the bridge can import adapters)
 *   AGENT_MEMORY_SERVER_URL  default http://127.0.0.1:8765
 *   AGENT_MEMORY_PROJECT_ID
 *   AGENT_MEMORY_WORKSPACE_ID
 *   AGENT_MEMORY_TASK_ID
 */
import { ChildProcess, spawn } from "node:child_process";
import * as os from "node:os";
import * as path from "node:path";

const REPO_ROOT =
  process.env.AGENT_MEMORY_REPO_ROOT ?? path.join(os.homedir(), "AgentMemory");

const BRIDGE_BATCH = path.join(
  REPO_ROOT,
  "plugins",
  "opencode",
  "opencode_bridge_batch.py",
);

let bridge: ChildProcess | null = null;
let bridgeBroken = false;

function ensureBridge(): ChildProcess | null {
  if (bridge && !bridgeBroken && bridge.exitCode === null) return bridge;
  bridgeBroken = false;
  bridge = spawn("python3", [BRIDGE_BATCH], {
    stdio: ["pipe", "inherit", "inherit"],
    env: process.env,
  });
  bridge.on("error", (err: Error) => {
    bridgeBroken = true;
    // eslint-disable-next-line no-console
    console.error("[agent-memory] bridge spawn error:", err.message);
  });
  bridge.on("close", () => {
    bridgeBroken = true;
  });
  return bridge;
}

/** Pipe one event to the long-lived bridge. Never blocks OpenCode. */
function emit(action: string, payload: Record<string, unknown>): void {
  if (bridgeBroken) return;
  const proc = ensureBridge();
  if (!proc || !proc.stdin.writable) return;
  const line = JSON.stringify({ action, payload }) + "\n";
  proc.stdin.write(line);
}

function closeBridge(): void {
  if (bridge && bridge.exitCode === null) {
    bridge.stdin?.end();
    bridge = null;
  }
}

export default function agentMemoryPlugin() {
  let sessionStarted = false;

  return {
    events: {
      async "session.start"(ctx: { sessionID: string; reason?: string }) {
        sessionStarted = true;
        emit("session_start", {
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
        emit("turn_end", {
          session_id: ctx.sessionID,
          run_id: ctx.sessionID,
          turn_index: 0,
        });
      },

      async "session.end"(ctx: { sessionID: string; reason?: string }) {
        emit("session_end", {
          session_id: ctx.sessionID,
          outcome: reasonToOutcome(ctx.reason),
        });
        sessionStarted = false;
        // Flush + terminate the bridge for this session.
        closeBridge();
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
