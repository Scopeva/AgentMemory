/**
 * agent-memory extension for Pi (TypeScript, no Python dependency).
 *
 * Pi extensions export a default factory function that receives
 * ExtensionAPI. The factory registers event handlers via pi.on().
 *
 * How it works:
 *   - Events are buffered in memory and flushed to the server's
 *     POST /v1/events/batch endpoint at session shutdown.
 *   - If the server is unreachable, events are spooled to a local
 *     JSONL file (~/.local/state/agent-memory/pi/spool.jsonl) and
 *     retried on the next flush.
 *
 * Env vars:
 *   AGENT_MEMORY_SERVER_URL   default http://127.0.0.1:8765
 *   AGENT_MEMORY_PROJECT_ID   optional — auto-detected from CWD if unset
 *   AGENT_MEMORY_WORKSPACE_ID
 *   AGENT_MEMORY_TASK_ID
 *   AGENT_MEMORY_SPOOL_ROOT   default ~/.local/state/agent-memory
 *
 * Drop this file into:
 *   ~/.pi/agent/extensions/agent-memory-pi.ts
 * or <project>/.pi/agent/extensions/agent-memory-pi.ts
 *
 * Pi loads it automatically (no separate install step if in the dir).
 */
import * as os from "node:os";
import * as path from "node:path";
import * as fs from "node:fs";

// ── config from env ────────────────────────────────────────────────────────
const SERVER_URL =
  process.env.AGENT_MEMORY_SERVER_URL ?? "http://127.0.0.1:8765";
const WORKSPACE_ID = process.env.AGENT_MEMORY_WORKSPACE_ID ?? undefined;
const TASK_ID = process.env.AGENT_MEMORY_TASK_ID ?? undefined;
const SPOOL_ROOT =
  process.env.AGENT_MEMORY_SPOOL_ROOT ??
  path.join(os.homedir(), ".local", "state", "agent-memory");

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

// ── event buffer ───────────────────────────────────────────────────────────
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
    agent: "pi",
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

function push(
  type: string,
  sessionId: string,
  runId: string,
  payload?: Record<string, unknown>,
): void {
  buffer.push(makeEvent(type, sessionId, runId, payload));
}

// ── spool (durable fallback) ───────────────────────────────────────────────
const SPOOL_FILE = path.join(SPOOL_ROOT, "pi", "spool.jsonl");

function writeSpool(events: AmEvent[]): void {
  try {
    fs.mkdirSync(path.dirname(SPOOL_FILE), { recursive: true });
    for (const e of events) {
      fs.appendFileSync(SPOOL_FILE, JSON.stringify(e) + "\n");
    }
  } catch (err) {
    console.error("[am-pi] spool write failed:", err);
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

// ── HTTP flush ─────────────────────────────────────────────────────────────
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
      console.error(`[am-pi] flush failed: HTTP ${resp.status}`);
      return false;
    }

    clearSpool();
    return true;
  } catch (err) {
    writeSpool(allEvents);
    console.error("[am-pi] server unreachable, spooling:", (err as Error).message);
    return false;
  }
}

// ── extraction guard (per-run, mirrors Python RunGuard) ──────────────────
const guards = new Map<string, { extractionAttempted: boolean; origin: string }>();

function allowExtraction(runId: string): boolean {
  let g = guards.get(runId);
  if (!g) {
    g = { extractionAttempted: false, origin: "user" };
    guards.set(runId, g);
  }
  if (g.origin === "memory_extraction") return false;
  if (g.extractionAttempted) return false;
  return true;
}

function markExtractionAttempted(runId: string): void {
  const g = guards.get(runId);
  if (g) {
    g.extractionAttempted = true;
    g.origin = "memory_extraction";
  }
}

function resetGuard(runId: string): void {
  guards.delete(runId);
}

// ── Pi factory (default export) ───────────────────────────────────────────
export default function agentMemoryExtension(
  pi: {
    on: (
      event: string,
      handler: (
        event: Record<string, unknown>,
        ctx: Record<string, unknown>,
      ) => void | Promise<void>,
    ) => () => void;
  },
): void {
  pi.on("session_start", (evt: Record<string, unknown>) => {
    const sessionId = String(evt.sessionId ?? evt.session_id ?? "");
    const nativeSessionId = String(evt.nativeSessionId ?? evt.native_session_id ?? "");
    if (sessionId) {
      push("session.start", sessionId, sessionId, {
        native_session_id: nativeSessionId,
      });
    }
  });

  pi.on("agent_start", (evt: Record<string, unknown>) => {
    const sessionId = String(evt.sessionId ?? evt.session_id ?? "");
    const runId = String(evt.runId ?? evt.run_id ?? sessionId);
    const headSha = String(evt.headSha ?? evt.head_sha ?? "");
    if (sessionId) {
      push("run.started", sessionId, runId, { head_sha_start: headSha });
    }
  });

  pi.on("turn_end", (evt: Record<string, unknown>) => {
    const sessionId = String(evt.sessionId ?? evt.session_id ?? "");
    const runId = String(evt.runId ?? evt.run_id ?? sessionId);
    const turnIndex = Number(evt.turnIndex ?? evt.turn_index ?? 0);
    if (sessionId) {
      push("turn.end", sessionId, runId, { turn_index: turnIndex });
    }
  });

  pi.on("agent_settled", (evt: Record<string, unknown>) => {
    const sessionId = String(evt.sessionId ?? evt.session_id ?? "");
    const runId = String(evt.runId ?? evt.run_id ?? sessionId);
    const outcome = String(evt.outcome ?? "completed");
    const headShaEnd = String(evt.headShaEnd ?? evt.head_sha_end ?? "");
    const hadCodeChanges = Boolean(evt.hadCodeChanges ?? evt.had_code_changes ?? false);
    const taskSignificant = Boolean(evt.taskSignificant ?? evt.task_significant ?? false);

    if (sessionId) {
      push("run.settled", sessionId, runId, {
        outcome,
        head_sha_end: headShaEnd,
      });

      // Decide if extraction should be requested
      if (allowExtraction(runId)) {
        if (
          (outcome === "completed" && hadCodeChanges) ||
          (outcome === "completed" && taskSignificant) ||
          outcome === "failed" ||
          outcome === "interrupted"
        ) {
          push("memory.extraction_requested", sessionId, runId, {});
          markExtractionAttempted(runId);
        }
      }
    }
  });

  pi.on("session_shutdown", (evt: Record<string, unknown>) => {
    const sessionId = String(evt.sessionId ?? evt.session_id ?? "");
    if (sessionId) {
      push("session.end", sessionId, sessionId, {});
    }
    // Fire-and-forget flush; never block Pi shutdown.
    void flushToServer();
  });
}

// ── named exports for programmatic use (optional) ────────────────────────
export { flushToServer, push, allowExtraction, markExtractionAttempted, resetGuard };
export type { AmEvent };
