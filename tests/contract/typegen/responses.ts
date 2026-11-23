import type { operations } from "./api";

export type ResponseBody<
  Operation extends keyof operations,
  Status extends keyof operations[Operation]["responses"],
> = operations[Operation]["responses"][Status] extends {
  content: { "application/json": infer Body };
}
  ? Body
  : never;
