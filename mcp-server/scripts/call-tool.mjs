#!/usr/bin/env node
import { CallToolResultSchema } from "@modelcontextprotocol/sdk/types.js";
import { withServer } from "./stdio-client.mjs";

try {
  const [name, json, ...extra] = process.argv.slice(2);
  if (!name || json === undefined || extra.length) {
    throw new Error("Usage: node scripts/call-tool.mjs <tool> '<json args>'");
  }
  const args = JSON.parse(json);
  if (!args || typeof args !== "object" || Array.isArray(args)) {
    throw new Error("Tool arguments must be a JSON object.");
  }

  const response = await withServer(async (client) => {
    await client.listTools({}, { timeout: 5_000 });
    return client.callTool({ name, arguments: args }, CallToolResultSchema, { timeout: 30_000 });
  });
  console.log(JSON.stringify({
    structuredContent: response.structuredContent ?? null,
    text: response.content.filter((item) => item.type === "text").map((item) => item.text).join("\n"),
    isError: response.isError === true,
  }));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
