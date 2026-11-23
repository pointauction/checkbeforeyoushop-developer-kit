"""Generate and compile TypeScript response assignments for every captured fixture."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from check_contract import FIXTURES_DIR, Contract, read_fixtures


def main():
    contract = Contract()
    fixtures = read_fixtures(FIXTURES_DIR)
    with TemporaryDirectory(prefix="cbys-typegen-") as directory:
        work = Path(directory)
        subprocess.run(
            ["npx", "--yes", "openapi-typescript@7.13.0", "openapi.yaml", "-o", str(work / "api.d.ts")],
            cwd=ROOT,
            check=True,
        )

        # Use object literals to give enum values their generated contextual types.
        # Every file goes through its own operation and status, including errors.
        shutil.copyfile(Path(__file__).with_name("responses.ts"), work / "responses.ts")
        with (work / "captures.ts").open("w", encoding="utf-8") as captures:
            captures.write('import type { ResponseBody } from "./responses";\n')
            for index, (path, fixture) in enumerate(fixtures.items()):
                status = fixture["status"]
                operation, _, _ = contract.response(path, status)
                payload = json.loads((FIXTURES_DIR / fixture["file"]).read_text(encoding="utf-8"))
                captures.write(f"\n// {path}\n")
                captures.write(
                    f"const capture{index}: ResponseBody<{json.dumps(operation)}, {status}>"
                    f" = {json.dumps(payload, indent=2)};\n"
                )

        subprocess.run(
            ["npx", "--yes", "-p", "typescript@5", "tsc", "--strict", "--noEmit", "captures.ts"],
            cwd=work,
            check=True,
        )
    print(f"TypeScript fixtures: {len(fixtures)} compiled.")


if __name__ == "__main__":
    main()
