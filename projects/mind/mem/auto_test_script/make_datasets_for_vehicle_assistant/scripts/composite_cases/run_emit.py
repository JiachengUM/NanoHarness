#!/usr/bin/env python3
"""Run an emit_*.py module's main() and write UTF-8 JSON to a file.

Usage (from datasets/):
  python run_emit.py emit_311_370.py handwritten_batches/batch_311_370.json
"""
from __future__ import annotations

import importlib.util
import sys
from io import StringIO
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python run_emit.py <emit_module.py> <out.json>", file=sys.stderr)
        return 1
    mod_path = Path(sys.argv[1]).resolve()
    out_path = Path(sys.argv[2]).resolve()
    spec = importlib.util.spec_from_file_location("emit_mod", mod_path)
    if spec is None or spec.loader is None:
        print("cannot load", mod_path, file=sys.stderr)
        return 1
    mod = importlib.util.module_from_spec(spec)
    sys.modules["emit_mod"] = mod
    spec.loader.exec_module(mod)
    buf = StringIO()
    old = sys.stdout
    sys.stdout = buf
    mod.main()
    sys.stdout = old
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(buf.getvalue(), encoding="utf-8")
    print(f"wrote {out_path} ({len(buf.getvalue())} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
