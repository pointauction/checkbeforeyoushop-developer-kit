import { access } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const entry = fileURLToPath(new URL("../dist/index.js", import.meta.url));

export async function withServer(run) {
  try {
    await access(entry);
  } catch {
    throw new Error("Built server missing. Run npm ci && npm run build in mcp-server.");
  }

  const env = {};
  for (const key of ["CBYS_FIXTURES_DIR", "CBYS_BASE_URL"]) {
    if (process.env[key] !== undefined) env[key] = process.env[key];
  }
  const transport = new StdioClientTransport({ command: process.execPath, args: [entry], env });
  const client = new Client({ name: "cbys-local-eval", version: "0.1.0" });
  let transportError;
  client.onerror = (error) => { transportError ??= error; };

  try {
    await client.connect(transport, { timeout: 5_000 });
    const result = await run(client);
    if (transportError) throw transportError;
    return result;
  } finally {
    await client.close();
  }
}
