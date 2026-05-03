"""One-shot scrubber: clear all outputs + redact known leaked secrets in trails/1_agent_test.ipynb."""
from __future__ import annotations

import json
import pathlib
import re

NB = pathlib.Path(__file__).parent / "trails" / "1_agent_test.ipynb"

# Patterns matching secrets we know are present + generic OpenAI / SK shapes.
SECRET_PATTERNS = [
    r"sk-(?:proj-|live-|test-)?[A-Za-z0-9_\-]{20,}",
    r"yJKJlZc3YNu5_ZErIyucEV3ICFfdXaTqdF6naQA5YoQ",
]
SECRET_RE = re.compile("|".join(SECRET_PATTERNS))


def main() -> None:
    nb = json.loads(NB.read_text(encoding="utf-8"))
    cleared = 0
    redacted_sources = 0
    redacted_outputs = 0

    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue

        # Clear outputs entirely — notebooks should never check in stdout.
        if cell.get("outputs"):
            for out in cell["outputs"]:
                blob = json.dumps(out)
                if SECRET_RE.search(blob):
                    redacted_outputs += 1
            cleared += 1
        cell["outputs"] = []
        cell["execution_count"] = None

        # Sanitize the source: don't print() raw secrets, and redact any literal
        # secret string that may have been pasted in.
        src = cell.get("source")
        if isinstance(src, list):
            src_str = "".join(src)
        else:
            src_str = src or ""
        new = src_str
        new = new.replace(
            'print(os.getenv("OPENAI_API_KEY"))',
            'print("OPENAI_API_KEY:", "set" if os.getenv("OPENAI_API_KEY") else "missing")',
        )
        if SECRET_RE.search(new):
            new = SECRET_RE.sub("<REDACTED>", new)
        if new != src_str:
            redacted_sources += 1
            cell["source"] = new.splitlines(keepends=True)

    NB.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    print("cells_with_outputs_cleared:", cleared)
    print("output_blocks_with_secret:", redacted_outputs)
    print("source_cells_redacted:", redacted_sources)


if __name__ == "__main__":
    main()
