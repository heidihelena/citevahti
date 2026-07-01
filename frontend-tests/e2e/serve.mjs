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

/* Isolate the engine's global config/state into the throwaway dir too: the panel calls
 * remember_root at startup, and without this the REAL ~/.config/citevahti/state.json
 * would point at this temp ledger after every run — the installed app would then open
 * the leftover test ledger instead of the user's project. */
const home = path.join(tmp, ".e2e-home");
fs.mkdirSync(home, { recursive: true });

const port = process.env.CV_E2E_PORT || "8123";
const python = process.env.PYTHON || "python";
const py = spawn(python, ["-m", "citevahti.panel.server", "--root", tmp, "--port", port],
  { stdio: "inherit", env: {
      ...process.env,
      PYTHONPATH: path.join(REPO, "src"),
      HOME: home,
      USERPROFILE: home,
      XDG_CONFIG_HOME: path.join(home, ".config"),
      XDG_STATE_HOME: path.join(home, ".local", "state"),
      LOCALAPPDATA: path.join(home, "AppData", "Local"),
    } });

const bye = () => { try { py.kill(); } catch {} try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} };
process.on("SIGTERM", bye); process.on("SIGINT", bye); process.on("exit", bye);
py.on("exit", (c) => process.exit(c ?? 0));
