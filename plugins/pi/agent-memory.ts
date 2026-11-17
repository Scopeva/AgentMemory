/**
 * agent-memory extension for Pi (TypeScript, no Python dependency).
 *
 * This replaces the old Python-based pi_extension.py + _pi_helper.py
 * approach which had environment issues inside Pi's JS/TS runtime.
 *
 * How it works:
 *   - One long-lived "batch bridge": events are buffered in-memory
 *     and flushed to the server's POST /v1/events/batch endpoint at
 *     session end (or periodically). No subprocess, no Python.
 *   - If the server is unreachable, events are written to a local
 *     spool file (~/.local/state/agent-memory/pi/spool.jsonl) and
 *     retried on next flush.
 *
 * Env vars:
 *   AGENT_MEMORY_SERVER_URL   default http://127.0.0.1:8765
 *   AGENT_MEMORY_PROJECT_ID   optional — auto-detected if unset
 *   AGENT_MEMORY_WORKSPACE_ID
 *   AGENT_MEMORY_TASK_ID
 *   AGENT_MEMORY_SPOOL_ROOT   default ~/.local/state/agent-memory
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

// Auto-detect project_id from CWD (mirrors detect_project_id() in Python)
function detectProjectId(): string {
  const explicit = process.env.AGENT_MEMORY_PROJECT_ID;
  if (explicit) return explicit;
  try {
    // Use the basename of the current working directory
    const cwd = process.cwd();
    return path.basename(cwd);
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

function nextSeq(): number {
  return ++seq;
}

function nowIso(): string {
  return new Date().toISOString().replace("T", " ").replace(/\.\d+Z$/, "");
}

function genUuid(): string {
  // Simple UUID v4 (no external dependency)
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
    sequence_no: nextSeq(),
    occurred_at: nowIso(),
    payload,
  };
}

function push(type: string, sessionId: string, runId: string, payload?: Record<string, unknown>): void {
  buffer.push(makeEvent(type, sessionId, runId, payload));
}

// ── spool (durable fallback) ───────────────────────────────────────────────
const SPOOL_FILE = path.join(SPOOL_ROOT, "pi", "spool.jsonl");

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
      // Server reachable but rejected — write everything back to spool
      writeSpool(allEvents);
      console.error(`[am-pi] flush failed: HTTP ${resp.status}`);
      return false;
    }

    clearSpool();
    return true;
  } catch (err) {
    // Server unreachable — spool everything
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

// ── public API (matches old pi_extension.py surface) ──────────────────────
export function onSessionStart(sessionId: string, nativeSessionId: string = ""): void {
  push("session.start", sessionId, sessionId, { native_session_id: nativeSessionId });
}

export function onRunStarted(runId: string, sessionId: string, headSha: string = ""): void {
  push("run.started", sessionId, runId, { head_sha_start: headSha });
}

export function onTurnEnd(runId: string, sessionId: string, turnIndex: number = 0): void {
  push("turn.end", sessionId, runId, { turn_index: turnIndex });
}

export function onSessionBeforeCompact(runId: string, sessionId: string, summary: string = ""): void {
  push("session.compacted", sessionId, runId, { pre_compact_summary: summary });
}

/**
 * Record that a run has settled. Returns { extract: boolean } so the
 * caller (Pi extension) knows whether to ask the model for extraction.
 */
export function onRunSettled(
  runId: string,
  sessionId: string,
  outcome: string,
  headShaEnd: string = "",
  hadCodeChanges: boolean = false,
  taskSignificant: boolean = false,
): { ok: boolean; extract: boolean } {
  push("run.settled", sessionId, runId, {
    outcome,
    head_sha_end: headShaEnd,
  });

  let extract = false;
  if (allowExtraction(runId)) {
    if (
      outcome === "completed" && hadCodeChanges ||
      outcome === "completed" && taskSignificant ||
      outcome === "failed" ||
      outcome === "interrupted"
    ) {
      push("memory.extraction_requested", sessionId, runId, {});
      markExtractionAttempted(runId);
      extract = true;
    }
  }

  return { ok: true, extract };
}

export function submitExtractionResult(
  runId: string,
  sessionId: string,
  captureResult: string,
  handoff?: Record<string, unknown>,
  memories?: Record<string, unknown>[],
): void {
  const payload: Record<string, unknown> = { capture_result: captureResult };
  if (handoff) payload["handoff"] = handoff;
  if (memories && memories.length > 0) payload["memories"] = memories;
  if (captureResult === "no_durable_memory") payload["result"] = "no_durable_memory";
  push("memory.extraction_completed", sessionId, runId, payload);
  resetGuard(runId);
}

export function onRunInterrupted(runId: string, sessionId: string, reason: string = ""): void {
  push("run.interrupted", sessionId, runId, { reason });
}

/**
 * Flush all buffered events to the server, then clear the buffer.
 * Call this on session shutdown.
 */
export async function onSessionShutdown(sessionId: string): Promise<boolean> {
  push("session.end", sessionId, sessionId, {});
  return flushToServer();
}

/**
 * Flush without emitting a session.end event (e.g. periodic checkpoint).
 */
export async function flush(): Promise<boolean> {
  return flushToServer();
}
