Below is a list of features currently implemented and some known limitations of the HTML app (the initial version of the list was compiled by a LLM).

### Build tab

Use the **Build** tab to:

- add modules manually,
- add subroutines manually,
- parse pasted `USE` statements, including `USE ... ONLY:` imports,
- handle multiline `USE` statements with continuation markers and ignore inline `!` comments,
- import JSON,
- export JSON,
- export DOT,
- clear cached graph data.

### Browse tab

Use the **Browse** tab to:

- search nodes,
- select a node,
- hide or restore nodes,
- identify modules, procedures, and external references.

### Inspect tab

Use the **Inspect** tab to:

- inspect incoming and outgoing dependencies,
- view relationship labels such as `USE`, `ONLY: symbol`, and containment links even in Minimal mode,
- rename nodes,
- hide or delete nodes,
- add or remove the selected node from the Quick Jump list,
- reset a customized Quick Jump list back to the automatic default,
- add per-node notes,
- add global notes,
- enable focus mode.

### Sidebar sizing

On desktop, the right sidebar can be resized by dragging its left-edge handle. This is useful when working with long module or subroutine names that would otherwise wrap or truncate in the **Browse**, **Inspect**, or **Quick Jump** sections.

### Layouts

FortGraph supports several Cytoscape layouts:

- Dagre left-to-right
- Dagre top-to-bottom
- Force-directed
- Breadth-first
- Circle
- Concentric
- Grid

### Path selection

Path-selection mode lets you select several nodes and highlight edges between them.

### Local storage

The viewer stores the following data in browser local storage:

- graph state,
- node positions,
- notes,
- hidden nodes,
- theme,
- display settings.

Clearing browser storage or changing browser profiles will remove that state. Export the graph as JSON when you need a portable copy.

## Additive JSON import

Imported JSON is merged with the current graph.

FortGraph:

- preserves existing nodes and edges,
- matches nodes by case-insensitive title,
- adds previously unseen nodes,
- remaps imported edge endpoints,
- skips duplicate edges with the same source, target, and label,
- adjusts conflicting IDs,
- offsets imported positions to reduce overlap.

Because matching is case-insensitive, `solver_mod` and `SOLVER_MOD` are treated as the same node during import.

## Circular dependencies

The parser and viewer allow circular dependencies.

For example:

```text
procedure_a → procedure_b
procedure_b → procedure_a
```

Cycles are preserved in the JSON and displayed in the graph.

## Parsing limitations

FortGraph uses a lightweight parser rather than a complete Fortran compiler frontend.

Known limitations include:

- Preprocessor branches are not evaluated.
- Generic interfaces may not resolve to a specific implementation.
- Procedure bindings may not resolve completely.
- Function-call inference is heuristic.
- Calls through procedure pointers may not resolve.
- Type-bound procedure calls may not resolve completely.
- Renamed imports are simplified to their remote symbol.
- Include files are not expanded automatically.
- Conditional compilation may produce inactive dependencies.
- Procedures with identical names in different scopes may be merged.

For compiler-grade semantic analysis, a full Fortran parser or compiler frontend would be required.