/**
 * agent-memory plugin for OpenCode (V2-compatible, V1-fallback).
 *
 * OpenCode 2.x loader requires the default export to have:
 *   - `id`: a string
 *   - `setup`: a function (or `effect`)
 *
 * Some OpenCode 2.x builds wrap the export via `Plugin.define()` (from
 * `@opencode/plugin`); others hand the raw object to the loader. To be
 * safe across both, this file:
 *
 *   1. Tries to get `Plugin` from `@opencode/plugin` (injected by the
 *      OpenCode runtime). If unavailable, falls back to a plain object
 *      export — the 2.x loader accepts both shapes.
 *   2. `setup(ctx)` registers 2.x `ctx.event.subscribe` handlers when
 *      available; as a V1 fallback it also returns a 1.x-style hooks
 *      object so OpenCode 1.18+ still works.
 *
 * Drop this file into:
 *   ~/.config/opencode/plugins/agent-memory.ts   (global, 2.x)
 *   <project>/.opencode/plugins/agent-memory.ts  (project-local, 2.x)
 *
 * How it works (batch bridge, #9):
 *   One long-lived Python bridge (`opencode_bridge_batch.py`) is spawned
 *   on session start. Every event is piped to its stdin as a JSON line;
 *   the bridge flushes on session end. No per-message process fork.
 *
 * Env vars (read by the Python bridge):
 *   AGENT_MEMORY_REPO_ROOT   path to the AgentMemory repo
 *   AGENT_MEMORY_SERVER_URL  default http://127.0.0.1:8765
 *   AGENT_MEMORY_PROJECT_ID
 *   AGENT_MEMORY_WORKSPACE_ID
 *   AGENT_MEMORY_TASK_ID
 */
import { ChildProcess, spawn } from "node:child_process";
import * as os from "node:os";
import * as path from "node:path";

// ── try to load Plugin from the injected @opencode/plugin ─────────────
// OpenCode injects this package at runtime; a bare import may fail if
// the plugin is type-checked or loaded outside the OpenCode process.
let Plugin: { define: (def: unknown) => unknown } | null = null;
try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const mod = require("@opencode/plugin");
  if (mod?.Plugin?.define) {
    Plugin = mod.Plugin;
  }
} catch {
  // not available — fall through to plain-object export
}

// ── bridge bookkeeping ───────────────────────────────────────────────────
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
    console.error("[agent-memory] bridge spawn error:", err.message);
  });
  bridge.on("close", () => {
    bridgeBroken = true;
  });
  return bridge;
}

function emit(action: string, payload: Record<string, unknown>): void {
  if (bridgeBroken) return;
  const proc = ensureBridge();
  if (!proc || !proc.stdin.writable) return;
  proc.stdin.write(JSON.stringify({ action, payload }) + "\n");
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

// ── event handlers (shared between 1.x hooks and 2.x subscribe) ────────
function makeHandlers() {
  const active = new Set<string>();

  const onSessionStart = (p: { sessionID?: string; reason?: string }) => {
    if (!p?.sessionID) return;
    active.add(p.sessionID);
    emit("session_start", {
      session_id: p.sessionID,
      native_session_id: p.reason ?? "",
    });
  };

  const onChatMessage = (p: {
    sessionID?: string;
    info?: { role?: string };
  }) => {
    if (!p?.sessionID || !active.has(p.sessionID)) return;
    if (p.info?.role !== "assistant") return;
    emit("turn_end", {
      session_id: p.sessionID,
      run_id: p.sessionID,
      turn_index: 0,
    });
  };

  const onSessionEnd = (p: { sessionID?: string; reason?: string }) => {
    if (!p?.sessionID) return;
    active.delete(p.sessionID);
    emit("session_end", {
      session_id: p.sessionID,
      outcome: reasonToOutcome(p.reason),
    });
    closeBridge();
  };

  return { onSessionStart, onChatMessage, onSessionEnd };
}

// ── plugin definition ────────────────────────────────────────────────────
const id = "agent-memory";

/**
 * V2 entry point. OpenCode calls `setup(ctx)` when the plugin loads.
 *
 * - If `ctx.event?.subscribe` exists (OpenCode 2.x), register handlers
 *   via the 2.x event bus.
 * - As a V1 fallback, `setup` also returns a 1.x-style hooks object;
 *   OpenCode 1.18.29+ merges it. Harmless in 2.x.
 */
async function setup(ctx: {
  event?: {
    subscribe?: (
      type: string,
      handler: (payload: unknown) => void | Promise<void>,
    ) => void;
  };
}): unknown {
  const { onSessionStart, onChatMessage, onSessionEnd } = makeHandlers();

  // 2.x: subscribe via ctx.event
  if (ctx?.event?.subscribe) {
    ctx.event.subscribe("session.start", onSessionStart);
    ctx.event.subscribe("chat.message", onChatMessage);
    ctx.event.subscribe("session.end", onSessionEnd);
  }

  // 1.x fallback: return hooks object so V1 loader can register them.
  return {
    events: {
      "session.start": onSessionStart,
      "chat.message": onChatMessage,
      "session.end": onSessionEnd,
    },
  };
}

// ── default export: prefer Plugin.define, fall back to plain object ────
const def = { id, setup };

export default Plugin?.define ? Plugin.define(def) : def;
