/**
 * agent-memory plugin for OpenCode (V2 API).
 *
 * OpenCode 2.x requires the default export to be `Plugin.define({ id, setup })`.
 * V1-style "function returning a hooks object" plugins are rejected with:
 *   "Plugin must export a default definition with an id and an effect or setup function."
 *
 * Drop this file into:
 *   ~/.config/opencode/plugins/agent-memory.ts   (global)
 *   <project>/.opencode/plugins/agent-memory.ts  (project-local)
 * OpenCode auto-discovers .opencode/plugins/ — no separate install step.
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
import { Plugin } from "@opencode/plugin";
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

export default Plugin.define({
  id: "agent-memory",

  async setup(ctx: {
    event?: {
      subscribe?: (
        type: string,
        handler: (payload: unknown) => void | Promise<void>,
      ) => void;
    };
  }) {
    const subscribe = ctx.event?.subscribe;
    if (!subscribe) {
      // ctx.event is optional; bail quietly if OpenCode has no event bus.
      return;
    }

    // Track sessions so we can mark session-scoped turns.
    const activeSessions = new Set<string>();

    subscribe("session.start", (payload: unknown) => {
      const p = payload as { sessionID?: string; reason?: string };
      const sid = p?.sessionID;
      if (!sid) return;
      activeSessions.add(sid);
      emit("session_start", {
        session_id: sid,
        native_session_id: p?.reason ?? "",
      });
    });

    subscribe("chat.message", (payload: unknown) => {
      const p = payload as {
        sessionID?: string;
        messageID?: string;
        info?: { role?: string };
      };
      const sid = p?.sessionID;
      if (!sid || !activeSessions.has(sid)) return;
      // Only record assistant turns as "turn.end" from the memory model's view.
      if (p?.info?.role !== "assistant") return;
      emit("turn_end", {
        session_id: sid,
        run_id: sid,
        turn_index: 0,
      });
    });

    subscribe("session.end", (payload: unknown) => {
      const p = payload as { sessionID?: string; reason?: string };
      const sid = p?.sessionID;
      if (!sid) return;
      activeSessions.delete(sid);
      emit("session_end", {
        session_id: sid,
        outcome: reasonToOutcome(p?.reason),
      });
      // Flush + terminate the bridge for this session.
      closeBridge();
    });
  },
});
