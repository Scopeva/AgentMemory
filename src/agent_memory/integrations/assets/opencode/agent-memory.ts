/**
 * Source-independent Agent Memory lifecycle bridge for OpenCode 2.x.
 *
 * OpenCode delivers server events through an async iterator. This plugin
 * records session and execution boundaries to Agent Memory; it deliberately
 * does not infer memory content from a transcript.
 */
import { Plugin } from "@opencode/plugin";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

const SERVER_URL = process.env.AGENT_MEMORY_SERVER_URL ?? "http://127.0.0.1:8765";
const WORKSPACE_ID = process.env.AGENT_MEMORY_WORKSPACE_ID ?? undefined;
const TASK_ID = process.env.AGENT_MEMORY_TASK_ID ?? undefined;
const SPOOL_FILE = path.join(
  process.env.AGENT_MEMORY_SPOOL_ROOT ?? path.join(os.homedir(), ".local", "state", "agent-memory"),
  "opencode",
  "spool.jsonl",
);
const EVENT_TYPES = [
  "session.created",
  "session.execution.started",
  "session.execution.succeeded",
  "session.execution.failed",
  "session.execution.interrupted",
  "session.step.ended",
] as const;

type AmEvent = {
  schema_version: "1.0";
  event_id: string;
  event_type: string;
  agent: "opencode";
  session_id: string;
  run_id: string;
  project_id: string;
  workspace_id?: string;
  task_id?: string;
  sequence_no: number;
  occurred_at: string;
  payload: Record<string, unknown>;
};

type LifecycleEvent = {
  type: string;
  data?: { sessionID?: string };
};

function projectId(directory: string): string {
  return process.env.AGENT_MEMORY_PROJECT_ID || path.basename(directory) || "unknown";
}

function readSpool(): AmEvent[] {
  try {
    return fs
      .readFileSync(SPOOL_FILE, "utf8")
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line) as AmEvent);
  } catch {
    return [];
  }
}

function writeSpool(events: AmEvent[]): void {
  try {
    fs.mkdirSync(path.dirname(SPOOL_FILE), { recursive: true });
    fs.appendFileSync(SPOOL_FILE, `${events.map(JSON.stringify).join("\n")}\n`);
  } catch (error) {
    console.error("[agent-memory] could not spool events:", error);
  }
}

function clearSpool(): void {
  try {
    fs.unlinkSync(SPOOL_FILE);
  } catch {
    // The spool is already absent.
  }
}

function createBridge(project_id: string) {
  let sequence = 0;
  const events: AmEvent[] = [];
  const started = new Set<string>();

  const push = (event_type: string, session_id: string, payload: Record<string, unknown> = {}) => {
    events.push({
      schema_version: "1.0",
      event_id: crypto.randomUUID(),
      event_type,
      agent: "opencode",
      session_id,
      run_id: session_id,
      project_id,
      workspace_id: WORKSPACE_ID,
      task_id: TASK_ID,
      sequence_no: ++sequence,
      occurred_at: new Date().toISOString(),
      payload,
    });
  };

  const begin = (session_id: string) => {
    if (started.has(session_id)) return;
    started.add(session_id);
    push("session.start", session_id, { native_session_id: session_id });
  };

  const flush = async (): Promise<void> => {
    const pending = [...readSpool(), ...events.splice(0)];
    if (!pending.length) return;
    try {
      const response = await fetch(`${SERVER_URL}/v1/events/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ events: pending }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      clearSpool();
    } catch (error) {
      writeSpool(pending);
      console.error("[agent-memory] event delivery deferred:", error);
    }
  };

  const handle = async (raw: unknown): Promise<void> => {
    const event = raw as LifecycleEvent;
    const session_id = event.data?.sessionID;
    if (!session_id) return;

    begin(session_id);
    if (event.type === "session.created") {
      await flush();
    } else if (event.type === "session.execution.started") {
      push("run.started", session_id);
    } else if (event.type === "session.step.ended") {
      push("turn.end", session_id);
    } else if (event.type.startsWith("session.execution.")) {
      const outcome = event.type.endsWith("succeeded")
        ? "completed"
        : event.type.endsWith("interrupted")
          ? "interrupted"
          : "failed";
      push("run.settled", session_id, { outcome });
      await flush();
    }
  };

  return { flush, handle };
}

export default Plugin.define({
  id: "agent-memory",
  setup(ctx) {
    const bridge = createBridge(projectId(ctx.location.directory));
    const controller = new AbortController();
    void (async () => {
      try {
        for await (const event of ctx.event.subscribe({
          types: [...EVENT_TYPES],
          signal: controller.signal,
        })) {
          await bridge.handle(event);
        }
      } catch (error) {
        if (!controller.signal.aborted) console.error("[agent-memory] event stream failed:", error);
      }
    })();
    return () => {
      controller.abort();
      void bridge.flush();
    };
  },
});
