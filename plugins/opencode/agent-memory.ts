/**
 * agent-memory plugin for OpenCode (V2-compatible, V1-fallback).
 *
 * Pure TypeScript — talks directly to the agent-memory server's HTTP
 * API (POST /v1/events/batch). No Python subprocess, no repo path.
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
 * How it works:
 *   Events are buffered in memory and flushed to the server via
 *   POST /v1/events/batch at session end. If the server is
 *   unreachable, events are spooled to a local JSONL file and
 *   retried on the next flush.
 *
 * Env vars:
 *   AGENT_MEMORY_SERVER_URL   default http://127.0.0.1:8765
 *   AGENT_MEMORY_PROJECT_ID   optional — auto-detected from CWD if unset
 *   AGENT_MEMORY_WORKSPACE_ID
 *   AGENT_MEMORY_TASK_ID
 *   AGENT_MEMORY_SPOOL_ROOT   default ~/.local/state/agent-memory
 */
import * as os from "node:os";
import * as path from "node:path";
import * as fs from "node:fs";

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

// ── config from env ────────────────────────────────────────────────────
const SERVER_URL =
  process.env.AGENT_MEMORY_SERVER_URL ?? "http://127.0.0.1:8765";
const WORKSPACE_ID = process.env.AGENT_MEMORY_WORKSPACE_ID ?? undefined;
const TASK_ID = process.env.AGENT_MEMORY_TASK_ID ?? undefined;
const SPOOL_ROOT =
  process.env.AGENT_MEMORY_SPOOL_ROOT ??
  path.join(os.homedir(), ".local", "state", "agent-memory");

// Auto-detect project_id from CWD (mirrors detect_project_id())
function detectProjectId(): string {
  const explicit = process.env.AGENT_MEMORY_PROJECT_ID;
  if (explicit) return explicit;
  try {
    return path.basename(process.cwd());
  } catch {
    return "unknown";
  }
}
const PROJECT_ID = detectProjectId();

// ── event buffer ───────────────────────────────────────────────────────
type AmEvent = {
  schema_version: string;
  event_id: string;
  event_type: string;
  agent: string;
  session_id: string;
  run_id: string;
  project_id?: string;
  workspace_id?: string;
  task_id?: string;
  sequence_no: number;
  occurred_at: string;
  payload: Record<string, unknown>;
};

let seq = 0;
const buffer: AmEvent[] = [];

function genUuid(): string {
  const b = globalThis.crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((v) => v.toString(16).padStart(2, "0"));
  return `${h[0]}${h[1]}${h[2]}${h[3]}-${h[4]}${h[5]}-${h[6]}${h[7]}-${h[8]}${h[9]}-${h.slice(10).join("")}`;
}

function makeEvent(
  type: string,
  sessionId: string,
  runId: string,
  payload: Record<string, unknown> = {},
): AmEvent {
  seq++;
  return {
    schema_version: "1.0",
    event_id: genUuid(),
    event_type: type,
    agent: "opencode",
    session_id: sessionId,
    run_id: runId,
    project_id: PROJECT_ID,
    workspace_id: WORKSPACE_ID,
    task_id: TASK_ID,
    sequence_no: seq,
    occurred_at: new Date().toISOString().replace("T", " ").replace(/\.\d+Z$/, ""),
    payload,
  };
}

function push(type: string, sessionId: string, runId: string, payload?: Record<string, unknown>): void {
  buffer.push(makeEvent(type, sessionId, runId, payload));
}

// ── spool (durable fallback) ───────────────────────────────────────────
const SPOOL_FILE = path.join(SPOOL_ROOT, "opencode", "spool.jsonl");

function ensureSpoolDir(): void {
  fs.mkdirSync(path.dirname(SPOOL_FILE), { recursive: true });
}

function writeSpool(events: AmEvent[]): void {
  try {
    ensureSpoolDir();
    for (const e of events) {
      fs.appendFileSync(SPOOL_FILE, JSON.stringify(e) + "\n");
    }
  } catch (err) {
    console.error("[agent-memory] spool write failed:", err);
  }
}

function readSpool(): AmEvent[] {
  try {
    if (!fs.existsSync(SPOOL_FILE)) return [];
    const lines = fs.readFileSync(SPOOL_FILE, "utf-8").trim().split("\n");
    return lines.filter(Boolean).map((l: string) => JSON.parse(l) as AmEvent);
  } catch {
    return [];
  }
}

function clearSpool(): void {
  try {
    if (fs.existsSync(SPOOL_FILE)) fs.unlinkSync(SPOOL_FILE);
  } catch {
    // ignore
  }
}

// ── HTTP flush ─────────────────────────────────────────────────────────
async function flushToServer(): Promise<boolean> {
  const allEvents = [...readSpool(), ...buffer.splice(0, buffer.length)];
  if (allEvents.length === 0) return true;

  try {
    const resp = await fetch(`${SERVER_URL}/v1/events/batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events: allEvents }),
    });

    if (!resp.ok) {
      writeSpool(allEvents);
      console.error(`[agent-memory] flush failed: HTTP ${resp.status}`);
      return false;
    }

    clearSpool();
    return true;
  } catch (err) {
    writeSpool(allEvents);
    console.error("[agent-memory] server unreachable, spooling:", (err as Error).message);
    return false;
  }
}

// ── event handlers ─────────────────────────────────────────────────────
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

function makeHandlers() {
  const active = new Set<string>();

  const onSessionStart = (raw: unknown) => {
    const p = raw as { sessionID?: string; reason?: string };
    if (!p?.sessionID) return;
    active.add(p.sessionID);
    push("session.start", p.sessionID, p.sessionID, {
      native_session_id: p.reason ?? "",
    });
  };

  const onChatMessage = (raw: unknown) => {
    const p = raw as { sessionID?: string; info?: { role?: string } };
    if (!p?.sessionID || !active.has(p.sessionID)) return;
    if (p.info?.role !== "assistant") return;
    push("turn.end", p.sessionID, p.sessionID, { turn_index: 0 });
  };

  const onSessionEnd = (raw: unknown) => {
    const p = raw as { sessionID?: string; reason?: string };
    if (!p?.sessionID) return;
    active.delete(p.sessionID);
    push("session.end", p.sessionID, p.sessionID, {
      outcome: reasonToOutcome(p.reason),
    });
    // Fire-and-forget flush; never block OpenCode.
    void flushToServer();
  };

  return { onSessionStart, onChatMessage, onSessionEnd };
}

// ── plugin definition ──────────────────────────────────────────────────
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
}): Promise<unknown> {
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

// ── default export: prefer Plugin.define, fall back to plain object ───
const def = { id, setup };

export default Plugin?.define ? Plugin.define(def) : def;
