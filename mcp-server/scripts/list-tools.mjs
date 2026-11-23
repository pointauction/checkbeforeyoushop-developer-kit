#!/usr/bin/env node
import { withServer } from "./stdio-client.mjs";

try {
  const tools = await withServer(async (client) => (
    await client.listTools({}, { timeout: 5_000 })
  ).tools);
  console.log(JSON.stringify(tools, null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
