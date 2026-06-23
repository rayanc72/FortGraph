#!/usr/bin/env python3
"""
Convert Fortran source files into JSON understood by the FortGraph HTML.

The parser is intentionally dependency-free and targets common modern Fortran syntax.
It recognizes:

- modules
- subroutines
- functions
- programs
- module/procedure containment
- USE dependencies, including ONLY lists
- CALL dependencies
- simple function references when --infer-functions is enabled

Examples
--------
Parse one file:
    python fortran_to_workflow_json.py solver.f90 -o solver.json

Parse several files:
    python fortran_to_workflow_json.py src/*.f90 -o project.json

Parse a source tree:
    python fortran_to_workflow_json.py src --recursive -o project.json

Include likely function-call references:
    python fortran_to_workflow_json.py src -r --infer-functions -o project.json
"""

### --rayan; June 2026

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


FORTRAN_SUFFIXES = {
    ".f", ".for", ".ftn", ".f77",
    ".f90", ".f95", ".f03", ".f08", ".f18",
    ".F", ".FOR", ".FTN", ".F77",
    ".F90", ".F95", ".F03", ".F08", ".F18",
}

INTRINSIC_MODULES = {
    "iso_c_binding",
    "iso_fortran_env",
    "ieee_arithmetic",
    "ieee_exceptions",
    "ieee_features",
    "omp_lib",
    "omp_lib_kinds",
    "openacc",
}

INTRINSIC_PROCEDURES = {
    "abs", "achar", "acos", "acosh", "adjustl", "adjustr", "aimag", "aint",
    "all", "allocated", "anint", "any", "asin", "asinh", "associated", "atan",
    "atan2", "atanh", "atomic_add", "atomic_and", "atomic_cas", "atomic_define",
    "atomic_fetch_add", "atomic_fetch_and", "atomic_fetch_or", "atomic_fetch_xor",
    "atomic_or", "atomic_ref", "atomic_xor", "bessel_j0", "bessel_j1", "bessel_jn",
    "bessel_y0", "bessel_y1", "bessel_yn", "bge", "bgt", "bit_size", "ble", "blt",
    "btest", "ceiling", "char", "cmplx", "command_argument_count", "conjg",
    "cos", "cosh", "count", "cpu_time", "cshift", "date_and_time", "dble",
    "digits", "dim", "dot_product", "dprod", "eoshift", "epsilon", "erf", "erfc",
    "erfc_scaled", "execute_command_line", "exp", "exponent", "extends_type_of",
    "findloc", "floor", "fraction", "gamma", "get_command", "get_command_argument",
    "get_environment_variable", "huge", "hypot", "iachar", "iall", "iand", "iany",
    "ibclr", "ibits", "ibset", "ichar", "ieor", "image_index", "index", "int",
    "ior", "iparity", "ishft", "ishftc", "is_iostat_end", "is_iostat_eor",
    "kind", "lbound", "leadz", "len", "len_trim", "lge", "lgt", "lle", "llt",
    "log", "log10", "log_gamma", "logical", "maskl", "maskr", "matmul", "max",
    "maxexponent", "maxloc", "maxval", "merge", "merge_bits", "min", "minexponent",
    "minloc", "minval", "mod", "modulo", "move_alloc", "mvbits", "nearest",
    "new_line", "nint", "norm2", "not", "null", "num_images", "pack", "parity",
    "popcnt", "poppar", "precision", "present", "product", "radix", "random_number",
    "random_seed", "range", "rank", "real", "repeat", "reshape", "rrspacing",
    "same_type_as", "scale", "scan", "selected_char_kind", "selected_int_kind",
    "selected_real_kind", "set_exponent", "shape", "shifta", "shiftl", "shiftr",
    "sign", "sin", "sinh", "size", "spacing", "spread", "sqrt", "storage_size",
    "sum", "system_clock", "tan", "tanh", "this_image", "tiny", "trailz",
    "transfer", "transpose", "trim", "ubound", "unpack", "verify",
}

KEYWORDS_THAT_LOOK_LIKE_CALLS = {
    "allocate", "associate", "block", "case", "class", "close", "critical",
    "deallocate", "do", "else", "elseif", "end", "entry", "error", "forall",
    "format", "if", "inquire", "interface", "open", "print", "read", "select",
    "stop", "sync", "then", "where", "write",
}

MODULE_RE = re.compile(
    r"^\s*module\s+(?!procedure\b|subroutine\b|function\b)([a-z_]\w*)\b",
    re.IGNORECASE,
)
SUBROUTINE_RE = re.compile(
    r"^\s*(?:(?:pure|elemental|recursive|impure|module)\s+)*"
    r"subroutine\s+([a-z_]\w*)\b",
    re.IGNORECASE,
)
FUNCTION_RE = re.compile(
    r"^\s*(?:(?:pure|elemental|recursive|impure|module)\s+)*"
    r"(?:(?:integer|real|complex|logical|character|double\s+precision|"
    r"type\s*\([^)]*\)|class\s*\([^)]*\))"
    r"(?:\s*\([^)]*\)|\s*\*\s*\w+)?\s+)?"
    r"function\s+([a-z_]\w*)\b",
    re.IGNORECASE,
)
PROGRAM_RE = re.compile(r"^\s*program\s+([a-z_]\w*)\b", re.IGNORECASE)
END_SCOPE_RE = re.compile(
    r"^\s*end\s*(module|subroutine|function|program)\b(?:\s+([a-z_]\w*))?",
    re.IGNORECASE,
)
USE_RE = re.compile(
    r"^\s*use\b"
    r"(?:\s*,\s*(?:intrinsic|non_intrinsic)\s*)?"
    r"\s*(?:::\s*)?"
    r"([a-z_]\w*)"
    r"(?:\s*,\s*only\s*:\s*(.*))?$",
    re.IGNORECASE,
)
CALL_RE = re.compile(r"\bcall\s+([a-z_]\w*)\b", re.IGNORECASE)
IDENT_CALL_RE = re.compile(r"\b([a-z_]\w*)\s*\(", re.IGNORECASE)


@dataclass
class Scope:
    kind: str
    name: str
    node_key: str
    parent_module: str | None = None


@dataclass
class Node:
    key: str
    title: str
    node_type: str
    parent_key: str | None = None
    parent_name: str | None = None
    order: int = 0
    files: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    label: str
    edge_type: str


class GraphBuilder:
    def __init__(
        self,
        *,
        include_intrinsic_modules: bool = False,
        infer_functions: bool = False,
    ) -> None:
        self.include_intrinsic_modules = include_intrinsic_modules
        self.infer_functions = infer_functions
        self.nodes: dict[str, Node] = {}
        self.edges: set[Edge] = set()
        self.defined_procedures: dict[str, str] = {}
        self.defined_modules: dict[str, str] = {}
        self.pending_calls: list[tuple[str, str, str]] = []
        self.pending_uses: list[tuple[str, str, list[str]]] = []
        self._counter = 0

    @staticmethod
    def key(kind: str, name: str) -> str:
        return f"{kind}:{name.casefold()}"

    def add_node(
        self,
        kind: str,
        name: str,
        *,
        parent_key: str | None = None,
        parent_name: str | None = None,
        source_file: str | None = None,
    ) -> str:
        normalized_kind = "module" if kind == "module" else (
            "external" if kind == "external" else "subroutine"
        )
        key = self.key(normalized_kind, name)
        existing = self.nodes.get(key)

        if existing is None:
            self._counter += 1
            existing = Node(
                key=key,
                title=name,
                node_type=normalized_kind,
                parent_key=parent_key,
                parent_name=parent_name,
                order=self._counter,
            )
            self.nodes[key] = existing
        else:
            if existing.node_type == "external" and normalized_kind != "external":
                old_key = existing.key
                new_key = self.key(normalized_kind, name)
                existing.node_type = normalized_kind
                existing.key = new_key
                existing.parent_key = parent_key or existing.parent_key
                existing.parent_name = parent_name or existing.parent_name
                self.nodes.pop(old_key, None)
                self.nodes[new_key] = existing
                self._replace_key(old_key, new_key)
                key = new_key
            elif parent_key and not existing.parent_key:
                existing.parent_key = parent_key
                existing.parent_name = parent_name

        if source_file:
            existing.files.add(source_file)

        if normalized_kind == "module":
            self.defined_modules[name.casefold()] = key
        elif normalized_kind == "subroutine":
            self.defined_procedures[name.casefold()] = key

        return key

    def _replace_key(self, old: str, new: str) -> None:
        self.edges = {
            Edge(
                new if edge.source == old else edge.source,
                new if edge.target == old else edge.target,
                edge.label,
                edge.edge_type,
            )
            for edge in self.edges
        }
        self.pending_calls = [
            (new if source == old else source, target, label)
            for source, target, label in self.pending_calls
        ]
        self.pending_uses = [
            (new if source == old else source, module, symbols)
            for source, module, symbols in self.pending_uses
        ]

    def add_edge(
        self,
        source: str,
        target: str,
        label: str,
        edge_type: str = "use",
    ) -> None:
        if source == target and label == "contains":
            return
        self.edges.add(Edge(source, target, label, edge_type))

    def parse_files(self, files: Sequence[Path]) -> None:
        for path in files:
            self.parse_file(path)
        self.resolve_references()

    def parse_file(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8", errors="replace")
        statements = logical_statements(text, fixed_form=is_fixed_form(path))
        stack: list[Scope] = []
        file_label = str(path)

        for statement in statements:
            clean = statement.strip()
            if not clean:
                continue

            end_match = END_SCOPE_RE.match(clean)
            if end_match:
                close_scope(stack, end_match.group(1).lower(), end_match.group(2))
                continue

            module_match = MODULE_RE.match(clean)
            if module_match:
                name = module_match.group(1)
                key = self.add_node("module", name, source_file=file_label)
                stack.append(Scope("module", name, key))
                continue

            sub_match = SUBROUTINE_RE.match(clean)
            if sub_match:
                name = sub_match.group(1)
                parent = nearest_module(stack)
                key = self.add_node(
                    "subroutine",
                    name,
                    parent_key=parent.node_key if parent else None,
                    parent_name=parent.name if parent else None,
                    source_file=file_label,
                )
                if parent:
                    self.add_edge(parent.node_key, key, "contains", "contains")
                stack.append(
                    Scope(
                        "subroutine",
                        name,
                        key,
                        parent_module=parent.name if parent else None,
                    )
                )
                continue

            function_match = FUNCTION_RE.match(clean)
            if function_match:
                name = function_match.group(1)
                parent = nearest_module(stack)
                key = self.add_node(
                    "subroutine",
                    name,
                    parent_key=parent.node_key if parent else None,
                    parent_name=parent.name if parent else None,
                    source_file=file_label,
                )
                if parent:
                    self.add_edge(parent.node_key, key, "contains", "contains")
                stack.append(
                    Scope(
                        "function",
                        name,
                        key,
                        parent_module=parent.name if parent else None,
                    )
                )
                continue

            program_match = PROGRAM_RE.match(clean)
            if program_match:
                name = program_match.group(1)
                key = self.add_node("subroutine", name, source_file=file_label)
                stack.append(Scope("program", name, key))
                continue

            current = nearest_dependency_scope(stack)
            if not current:
                continue

            use_match = USE_RE.match(clean)
            if use_match:
                module_name = use_match.group(1)
                if (
                    not self.include_intrinsic_modules
                    and module_name.casefold() in INTRINSIC_MODULES
                ):
                    continue
                symbols = parse_only_symbols(use_match.group(2) or "")
                self.pending_uses.append(
                    (current.node_key, module_name, symbols)
                )
                continue

            for called in CALL_RE.findall(clean):
                self.pending_calls.append(
                    (current.node_key, called, f"CALL {called}")
                )

            if self.infer_functions and not declaration_like(clean):
                for candidate in IDENT_CALL_RE.findall(clean):
                    name = candidate.casefold()
                    if (
                        name in INTRINSIC_PROCEDURES
                        or name in KEYWORDS_THAT_LOOK_LIKE_CALLS
                        or re.search(rf"\bcall\s+{re.escape(candidate)}\b", clean, re.I)
                    ):
                        continue
                    self.pending_calls.append(
                        (current.node_key, candidate, f"FUNC {candidate}")
                    )

    def resolve_references(self) -> None:
        for source, module_name, symbols in self.pending_uses:
            module_key = self.defined_modules.get(module_name.casefold())
            if module_key is None:
                module_key = self.add_node("external", module_name)

            if symbols:
                for symbol in symbols:
                    target_key = self.defined_procedures.get(symbol.casefold())
                    if target_key is None:
                        target_key = self.add_node("external", symbol)
                    self.add_edge(source, target_key, f"ONLY: {symbol}", "use")
                    self.add_edge(target_key, module_key, "in", "contains")
            else:
                self.add_edge(source, module_key, "USE", "use")

        for source, called_name, label in self.pending_calls:
            target_key = self.defined_procedures.get(called_name.casefold())
            if target_key is None:
                target_key = self.add_node("external", called_name)
            self.add_edge(source, target_key, label, "use")

    def as_json(self) -> dict:
        ordered_nodes = sorted(self.nodes.values(), key=lambda node: node.order)
        id_by_key = {
            node.key: f"n-{index:05d}"
            for index, node in enumerate(ordered_nodes, start=1)
        }

        levels = {
            "module": 0,
            "subroutine": 1,
            "external": 2,
        }
        type_counts = {"module": 0, "subroutine": 0, "external": 0}
        nodes_json = []

        for node in ordered_nodes:
            row = type_counts[node.node_type]
            type_counts[node.node_type] += 1
            nodes_json.append(
                {
                    "id": id_by_key[node.key],
                    "type": node.node_type,
                    "title": node.title,
                    "parentId": id_by_key.get(node.parent_key),
                    "parentName": node.parent_name,
                    "position": {
                        "x": 120 + row * 230,
                        "y": 120 + levels[node.node_type] * 220,
                    },
                }
            )

        edges_json = []
        valid_keys = set(id_by_key)
        for index, edge in enumerate(
            sorted(
                (
                    edge for edge in self.edges
                    if edge.source in valid_keys and edge.target in valid_keys
                ),
                key=lambda edge: (
                    id_by_key[edge.source],
                    id_by_key[edge.target],
                    edge.label.casefold(),
                ),
            ),
            start=1,
        ):
            edges_json.append(
                {
                    "id": f"e-{index:05d}",
                    "source": id_by_key[edge.source],
                    "target": id_by_key[edge.target],
                    "label": edge.label,
                    "type": edge.edge_type,
                }
            )

        return {
            "version": 2,
            "nodes": nodes_json,
            "edges": edges_json,
        }


def strip_inline_comment(line: str) -> str:
    result: list[str] = []
    quote: str | None = None
    index = 0

    while index < len(line):
        char = line[index]
        if quote:
            result.append(char)
            if char == quote:
                if index + 1 < len(line) and line[index + 1] == quote:
                    result.append(line[index + 1])
                    index += 2
                    continue
                quote = None
            index += 1
            continue

        if char in {"'", '"'}:
            quote = char
            result.append(char)
        elif char == "!":
            break
        else:
            result.append(char)
        index += 1

    return "".join(result)


def logical_statements(text: str, *, fixed_form: bool) -> list[str]:
    if fixed_form:
        return fixed_form_statements(text)
    return free_form_statements(text)


def free_form_statements(text: str) -> list[str]:
    statements: list[str] = []
    pending = ""

    for raw in text.splitlines():
        line = strip_inline_comment(raw).rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        stripped = line.strip()
        leading_continuation = stripped.startswith("&")
        if leading_continuation:
            stripped = stripped[1:].lstrip()

        continues = stripped.endswith("&")
        if continues:
            stripped = stripped[:-1].rstrip()

        if pending:
            pending = f"{pending} {stripped}".strip()
        else:
            pending = stripped

        if not continues:
            statements.extend(split_semicolons(pending))
            pending = ""

    if pending:
        statements.extend(split_semicolons(pending))

    return statements


def fixed_form_statements(text: str) -> list[str]:
    statements: list[str] = []
    pending = ""

    for raw in text.splitlines():
        expanded = raw.expandtabs(8)
        if not expanded:
            continue
        first = expanded[0]
        if first in {"c", "C", "*", "!"}:
            continue
        if expanded.lstrip().startswith("#"):
            continue

        continuation = len(expanded) > 5 and expanded[5] not in {" ", "0"}
        body = expanded[6:72] if len(expanded) > 6 else ""
        body = strip_inline_comment(body).strip()
        if not body:
            continue

        if continuation and pending:
            pending = f"{pending} {body}".strip()
        else:
            if pending:
                statements.extend(split_semicolons(pending))
            pending = body

    if pending:
        statements.extend(split_semicolons(pending))

    return statements


def split_semicolons(statement: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None

    for char in statement:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            current.append(char)
        elif char == ";":
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
        else:
            current.append(char)

    part = "".join(current).strip()
    if part:
        parts.append(part)
    return parts


def parse_only_symbols(text: str) -> list[str]:
    symbols = []
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        if "=>" in item:
            local_name, remote_name = map(str.strip, item.split("=>", 1))
            symbol = remote_name or local_name
        else:
            symbol = item
        match = re.match(r"([a-z_]\w*)", symbol, re.IGNORECASE)
        if match:
            symbols.append(match.group(1))
    return symbols


def declaration_like(statement: str) -> bool:
    lowered = statement.lstrip().casefold()
    prefixes = (
        "integer", "real", "complex", "logical", "character", "type",
        "class", "procedure", "external", "intrinsic", "dimension",
        "parameter", "public", "private", "interface", "module procedure",
        "subroutine", "function", "program", "use", "implicit",
    )
    return lowered.startswith(prefixes) or "::" in lowered


def nearest_module(stack: Sequence[Scope]) -> Scope | None:
    return next(
        (scope for scope in reversed(stack) if scope.kind == "module"),
        None,
    )


def nearest_dependency_scope(stack: Sequence[Scope]) -> Scope | None:
    return next(
        (
            scope for scope in reversed(stack)
            if scope.kind in {"subroutine", "function", "program", "module"}
        ),
        None,
    )


def close_scope(
    stack: list[Scope],
    kind: str,
    name: str | None,
) -> None:
    target_name = name.casefold() if name else None
    for index in range(len(stack) - 1, -1, -1):
        scope = stack[index]
        kind_matches = scope.kind == kind or (
            kind in {"subroutine", "function"} and
            scope.kind in {"subroutine", "function"}
        )
        name_matches = target_name is None or scope.name.casefold() == target_name
        if kind_matches and name_matches:
            del stack[index:]
            return


def is_fixed_form(path: Path) -> bool:
    return path.suffix.casefold() in {".f", ".for", ".ftn", ".f77"}


def collect_files(inputs: Sequence[Path], recursive: bool) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()

    for item in inputs:
        if not item.exists():
            raise FileNotFoundError(f"Input does not exist: {item}")

        candidates: Iterable[Path]
        if item.is_dir():
            pattern = "**/*" if recursive else "*"
            candidates = item.glob(pattern)
        else:
            candidates = [item]

        for path in candidates:
            if (
                path.is_file()
                and path.suffix in FORTRAN_SUFFIXES
                and path.resolve() not in seen
            ):
                files.append(path)
                seen.add(path.resolve())

    return sorted(files, key=lambda path: str(path).casefold())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Parse Fortran source and generate JSON for the "
            "Fortran Dependency Tracker HTML."
        )
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Fortran source file(s) or source directories.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("fortran-deps.json"),
        help="Output JSON path (default: fortran-deps.json).",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively scan input directories.",
    )
    parser.add_argument(
        "--include-intrinsic-modules",
        action="store_true",
        help="Include ISO/IEEE/OpenMP intrinsic modules as external nodes.",
    )
    parser.add_argument(
        "--infer-functions",
        action="store_true",
        help=(
            "Infer likely function calls from name(...). This can add false "
            "positives for arrays and type constructors."
        ),
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation width (default: 2).",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        files = collect_files(args.inputs, args.recursive)
    except FileNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if not files:
        print("error: no Fortran source files found", file=sys.stderr)
        return 2

    graph = GraphBuilder(
        include_intrinsic_modules=args.include_intrinsic_modules,
        infer_functions=args.infer_functions,
    )
    graph.parse_files(files)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(graph.as_json(), indent=args.indent) + "\n",
        encoding="utf-8",
    )

    print(
        f"Wrote {args.output} "
        f"({len(graph.nodes)} nodes, {len(graph.edges)} edges, "
        f"{len(files)} source file{'s' if len(files) != 1 else ''})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
