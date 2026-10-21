import { spawn } from "node:child_process";
import { cpSync, existsSync } from "node:fs";
import { join } from "node:path";

const root = process.cwd();
const standalone = join(root, ".next", "standalone");
const server = join(standalone, "server.js");
const staticSource = join(root, ".next", "static");

if (!existsSync(server) || !existsSync(staticSource)) {
  console.error("Build the site with `npm run build` before starting it.");
  process.exit(1);
}

// Next's standalone output omits static and public assets by design.
cpSync(staticSource, join(standalone, ".next", "static"), { recursive: true });
const publicSource = join(root, "public");
if (existsSync(publicSource)) cpSync(publicSource, join(standalone, "public"), { recursive: true });

const child = spawn(process.execPath, [server], {
  cwd: standalone,
  env: process.env,
  stdio: "inherit"
});

for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
child.on("exit", (code) => process.exit(code ?? 1));
