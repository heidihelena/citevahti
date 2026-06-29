/* Playwright webServer command: serve the real panel against a THROWAWAY copy of the demo
 * ledger, so e2e exports/edits never touch the repo. */
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..");
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "cv-e2e-"));
fs.cpSync(path.join(REPO, ".demo-ledger"), tmp, { recursive: true });

const port = process.env.CV_E2E_PORT || "8123";
const python = process.env.PYTHON || "python";
const py = spawn(python, ["-m", "citevahti.panel.server", "--root", tmp, "--port", port],
  { stdio: "inherit", env: { ...process.env, PYTHONPATH: path.join(REPO, "src") } });

const bye = () => { try { py.kill(); } catch {} try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} };
process.on("SIGTERM", bye); process.on("SIGINT", bye); process.on("exit", bye);
py.on("exit", (c) => process.exit(c ?? 0));
