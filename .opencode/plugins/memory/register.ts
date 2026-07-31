/**
 * OpenCode plugin entry point — the module the OpenCode runtime loads.
 *
 * opencode resolves the plugin directory via `package.json` -> `main` and
 * imports that module. The runtime calls the module's *sole* default export
 * with a `PluginInput` (`{ client, project, worktree, directory, serverUrl, $ }`)
 * and expects a `Hooks` object in return. Empirically (opencode 1.18.x) a
 * plugin module must export exactly one entry — extra named exports prevent
 * loading — so all pure/testable logic lives in `./index.ts` and this file only
 * adapts it to the runtime.
 *
 * Implements openspec/specs/memory-triggers/spec.md and
 * openspec/specs/opencode-plugin/spec.md:
 *   - session.created: project name resolution only (no memory auto-injection)
 *   - session.idle: checkpoint reminder via tui prompt (skip if no activity or
 *     already delivered)
 *   - tool.execute.after: detect `git commit*` and queue a checkpoint
 *   - experimental.chat.messages.transform: deliver queued checkpoints and the
 *     explicit prompt triggers (`/brain`, `/checkpoint`, `recuerdo que ...`)
 *     on the next turn (works headless and in TUI)
 *   - experimental.session.compacting: pre-compaction capture (always fires)
 *   - server.instance.disposed: run the post-session digest (detached spawn)
 *   - OpenCode version guard: warn on < 1.17.10, disable gracefully
 */

import { spawn } from "node:child_process";
import { writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  createSessionState,
  resolveProjectName,
  idleCheckpoint,
  compactingCheckpoint,
  isGitCommit,
  buildCheckpointPrompt,
  buildCommitCheckpointPrompt,
  isSupportedVersion,
  type SessionState,
} from "./index";

const PLUGIN_NAME = "obsidian-second-brain";
const MIN_OPENCODE_VERSION = "1.17.10";
const REPO_ROOT = "/home/hiro03/Private/Projects/ObsidianSecondBraind";
const DIGEST_SCRIPT = join(REPO_ROOT, "scripts", "digest_session.py");
const ACTIVITY_MAX_LINES = 20;
const ACTIVITY_MAX_CHARS = 80;
const MCP_UNREACHABLE = "> ⚠️ Memory server unreachable — search cannot be completed.";
const NO_ACTIVITY_REPLY =
  "No tracked activity in this session. Nothing to checkpoint.";

// ── Local structural types (the @opencode-ai/plugin package is not a
//    dependency of this plugin directory; keep the surface minimal). ────────

type TextPart = { type: "text"; text: string };
type MessageLike = {
  info: { role: string; sessionID: string };
  parts?: TextPart[];
};

function textOf(parts: TextPart[] | undefined): string {
  return (parts ?? [])
    .filter((p) => p?.type === "text" && typeof p.text === "string")
    .map((p) => p.text)
    .join("\n");
}

export default async function registerPlugin(input: {
  client: any;
  project?: any;
  worktree?: string;
  directory?: string;
}): Promise<{
  dispose?: () => Promise<void>;
  event?: (input: { event: any }) => Promise<void>;
  "tool.execute.after"?: (input: {
    tool: string;
    sessionID: string;
    args: any;
  }) => Promise<void>;
  "experimental.session.compacting"?: (
    input: { sessionID: string },
    output: { context: string[] },
  ) => Promise<void>;
  "experimental.chat.messages.transform"?: (
    _input: {},
    output: { messages: MessageLike[] },
  ) => Promise<void>;
  "command.execute.before"?: (
    input: { command: string; sessionID: string; arguments: string },
    output: { parts: TextPart[] },
  ) => Promise<void>;
}> {
  const client = input.client;
  const log = (...msg: string[]) => console.log(`[${PLUGIN_NAME}]`, ...msg);

  // ── Version guard (from `installation.updated` / `session.created`) ───────
  let supported = true;
  let versionChecked = false;
  const checkVersion = (version: string) => {
    if (versionChecked || typeof version !== "string") return;
    versionChecked = true;
    if (!isSupportedVersion(version)) {
      supported = false;
      console.warn(
        `[${PLUGIN_NAME}] OpenCode ${version} < ${MIN_OPENCODE_VERSION}: ` +
          "memory plugin disabled (unsupported version).",
      );
    } else {
      log(`OpenCode ${version} >= ${MIN_OPENCODE_VERSION} — plugin active.`);
    }
  };

  // ── Per-session state ─────────────────────────────────────────────────────
  const states = new Map<string, SessionState>();
  const activities = new Map<string, string[]>();
  const queued = new Map<string, string>();
  const sessionDirs = new Map<string, string>();
  const projectCache = new Map<string, string>();

  const track = (sessionID: string, line: string) => {
    const state = states.get(sessionID);
    if (!state) return;
    state.hasActivity = true;
    const list = activities.get(sessionID) ?? [];
    if (!list.includes(line)) {
      list.push(line);
      if (list.length > ACTIVITY_MAX_LINES) list.shift();
      activities.set(sessionID, list);
    }
  };

  const summary = (sessionID: string): string =>
    (activities.get(sessionID) ?? []).join("\n");

  const projectFor = async (directory: string): Promise<string> => {
    const cached = projectCache.get(directory);
    if (cached) return cached;
    const project = await resolveProjectName(directory || input.directory || "");
    projectCache.set(directory, project);
    return project;
  };

  // ── Prompt-trigger directives (agent performs the actual MCP calls) ───────
  const checkpointDirective = (sessionID: string): string => {
    const state = states.get(sessionID);
    if (!state || !state.hasActivity) {
      return `> [memory-checkpoint] ${NO_ACTIVITY_REPLY}`;
    }
    return buildCheckpointPrompt(state, summary(sessionID));
  };

  const brainDirective = (raw: string): string => {
    const rest = raw
      .replace(/^\/brain\b/, "")
      .replace(/^recuerdo que\b/i, "")
      .trim();
    const first = rest.split(/\s+/)[0] ?? "";
    const kind = ["search", "recall", "profile"].includes(first) ? first : "";
    const query = (kind ? rest.replace(kind, "").trim() : rest) || "(whole prompt)";
    const target =
      kind === "profile"
        ? "get_profile"
        : kind === "recall"
          ? "export_memories"
          : "search_memory";
    return [
      "> 🧠 Memory request via prompt trigger.",
      `> Query: ${query}`,
      `> Use the memory-server MCP tools. First call the ping tool (2s timeout); ` +
        `if it fails, reply exactly with "${MCP_UNREACHABLE}" and stop.`,
      `> Otherwise call \`${target}\` and summarize the results.`,
      `> Omit the \`project\` parameter to search across ALL projects (cross-project memory). Only specify project if the user explicitly asks for a specific project's entries.`,
    ].join("\n");
  };

  // ── Post-session digest (detached: survives the app exiting) ──────────────
  const transcriptOf = (messages: any[]): string =>
    (messages ?? [])
      .map((m) => {
        const role = m?.role === "assistant" ? "assistant" : "user";
        const text = textOf(m?.parts).trim();
        return text ? `## ${role}\n${text}` : null;
      })
      .filter((l): l is string => l !== null)
      .join("\n\n");

  const spawnDigest = (transcriptPath: string, project: string) => {
    spawn(
      "uv",
      [
        "run",
        "--directory",
        REPO_ROOT,
        "python",
        DIGEST_SCRIPT,
        "--transcript",
        transcriptPath,
        "--project",
        project,
      ],
      { cwd: REPO_ROOT, detached: true, stdio: "ignore" },
    ).unref();
  };

  const digestSessions = async () => {
    for (const [sessionID, directory] of sessionDirs) {
      try {
        const project = await projectFor(directory);
        const res = await client.session.messages({ path: { id: sessionID } });
        const messages = Array.isArray(res) ? res : (res?.data ?? []);
        const transcript = transcriptOf(messages);
        if (!transcript.trim()) continue;
        const tmpPath = join(tmpdir(), `opencode-digest-${sessionID}.txt`);
        await writeFile(tmpPath, transcript, "utf-8");
        spawnDigest(tmpPath, project);
      } catch (err) {
        console.warn(
          `[${PLUGIN_NAME}] digest failed for ${sessionID}:`,
          err instanceof Error ? err.message : err,
        );
      }
    }
  };

  // ── Hooks ─────────────────────────────────────────────────────────────────
  return {
    event: async ({ event }: { event: any }) => {
      if (!supported) return;
      switch (event?.type) {
        case "installation.updated":
          checkVersion(event.properties?.version);
          break;
        case "session.created": {
          const info = event.properties?.info;
          const sessionID = event.properties?.sessionID;
          const directory = info?.directory ?? "";
          if (!sessionID) break;
          checkVersion(info?.version);
          const project = await projectFor(directory);
          if (!states.has(sessionID)) {
            states.set(sessionID, createSessionState(project));
            activities.set(sessionID, []);
          }
          sessionDirs.set(sessionID, directory);
          break;
        }
        case "session.idle": {
          const sessionID = event.properties?.sessionID;
          const state = states.get(sessionID);
          if (!state) break;
          const text = idleCheckpoint(state, summary(sessionID));
          if (text) {
            try {
              await client.tui.appendPrompt({ body: { text } });
            } catch {
              // headless: no TUI prompt to append to; the reminder is best-effort
            }
          }
          break;
        }
      }
    },

    "tool.execute.after": async ({ tool, sessionID, args }) => {
      if (!supported || !sessionID) return;
      if (tool === "bash" && typeof args?.command === "string") {
        const command = args.command;
        if (isGitCommit(command)) {
          const state = states.get(sessionID);
          if (state) {
            state.hasActivity = true;
            queued.set(sessionID, buildCommitCheckpointPrompt(state));
          }
        } else {
          track(sessionID, `bash: ${command.trim().slice(0, ACTIVITY_MAX_CHARS)}`);
        }
        return;
      }
      if (tool === "edit" || tool === "write") {
        const file = typeof args?.filePath === "string" ? args.filePath : "";
        track(sessionID, `${tool}: ${file || args?.file || "(unknown file)"}`);
      }
    },

    "experimental.session.compacting": async (_input, output) => {
      if (!supported) return;
      const sessionID = (_input as { sessionID: string }).sessionID;
      const state = states.get(sessionID);
      if (!state) return;
      const text = compactingCheckpoint(state, summary(sessionID));
      if (text) output.context.push(text);
    },

    "experimental.chat.messages.transform": async (_input, output) => {
      if (!supported) return;
      const last = output.messages[output.messages.length - 1];
      if (!last || last.info?.role !== "user") return;
      const sessionID = last.info.sessionID;
      const text = textOf(last.parts);
      const injections: string[] = [];

      const queuedText = queued.get(sessionID);
      if (queuedText) {
        queued.delete(sessionID);
        injections.push(queuedText);
      }
      if (/\/brain(?:\s|$)/.test(text)) injections.push(brainDirective(text));
      if (/\/checkpoint(?:\s|$)/.test(text)) {
        injections.push(checkpointDirective(sessionID));
      }
      if (/recuerdo que/i.test(text)) injections.push(brainDirective(text));

      if (injections.length > 0) {
        last.parts = [
          ...(last.parts ?? []),
          ...injections.map((t): TextPart => ({ type: "text", text: t })),
        ];
      }
    },

    "command.execute.before": async ({ command, sessionID, arguments: args }, output) => {
      if (!supported) return;
      if (command === "checkpoint") {
        output.parts = [...output.parts, { type: "text", text: checkpointDirective(sessionID) }];
      } else if (command === "brain") {
        output.parts = [
          ...output.parts,
          { type: "text", text: brainDirective(`/brain ${args ?? ""}`) },
        ];
      }
    },

    dispose: async () => {
      if (!supported) return;
      await digestSessions();
    },
  };
}
