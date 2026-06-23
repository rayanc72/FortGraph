# Basic FortGraph example

This directory contains a small Fortran project and its corresponding FortGraph JSON representation.

## Files

- `sample_project.f90` — short Fortran source example
- `sample_project.json` — corresponding FortGraph dependency graph
- `fortgraph.schema.json` — formal JSON Schema for FortGraph graph files

## Generate the graph

From the repository root:

```bash
python3 fortran_to_workflow.py \
  examples/basic/sample_project.f90 \
  -o examples/basic/sample_project.generated.json
```

Then open `FortGraph.html` and import:

```text
examples/basic/sample_project.generated.json
```

The generated graph should include:

- `math_utils`
- `square`
- `print_square`
- `simulation`
- `run_simulation`
- `main`

It should also include module-containment edges, `USE ... ONLY:` relationships, and direct `CALL` relationships.
