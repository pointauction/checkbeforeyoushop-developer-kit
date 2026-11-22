#!/usr/bin/env node
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createMcpServer } from "./server.js";

try {
  await createMcpServer().connect(new StdioServerTransport());
} catch {
  console.error("Could not start the CheckBeforeYouShop MCP server.");
  process.exitCode = 1;
}
