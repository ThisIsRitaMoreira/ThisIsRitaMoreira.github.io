"""Turn the percent-format sources in fabric/src/*.py into Fabric-ready .ipynb notebooks.

Cells start with '# %%'. '# %% [markdown]' makes a markdown cell (leading '# ' stripped);
'# %% tags=["parameters"]' makes a parameters cell.

Usage:  python -I fabric/tools/build_notebooks.py fabric/src fabric/notebooks
"""
import json
import re
import sys
from pathlib import Path

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
META = {
    "kernel_info": {"name": "synapse_pyspark"},
    "kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark", "language": "Python"},
    "language_info": {"name": "python"},
    "microsoft": {"language": "python", "language_group": "synapse_pyspark"},
}


def cells_of(text):
    cells, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^# %%(.*)$", line)
        if m:
            if cur:
                cells.append(cur)
            head = m.group(1)
            cur = {"kind": "markdown" if "[markdown]" in head else "code",
                   "tags": ["parameters"] if "parameters" in head else [], "lines": []}
            continue
        if cur is not None:
            cur["lines"].append(line)
    if cur:
        cells.append(cur)
    out = []
    for i, c in enumerate(cells):
        lines = c["lines"]
        while lines and not lines[-1].strip():
            lines.pop()
        while lines and not lines[0].strip():
            lines.pop(0)
        if c["kind"] == "markdown":
            lines = [re.sub(r"^# ?", "", ln) for ln in lines]
        src = [ln + "\n" for ln in lines]
        if src:
            src[-1] = src[-1].rstrip("\n")
        cell = {"cell_type": c["kind"], "id": f"c{i:02d}", "metadata": {"tags": c["tags"]} if c["tags"] else {},
                "source": src}
        if c["kind"] == "code":
            cell.update({"execution_count": None, "outputs": []})
        out.append(cell)
    return out


OUT.mkdir(parents=True, exist_ok=True)
for py in sorted(SRC.glob("*.py")):
    nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": META, "cells": cells_of(py.read_text(encoding="utf-8"))}
    dst = OUT / (py.stem + ".ipynb")
    dst.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{dst}  ({len(nb['cells'])} cells)")
