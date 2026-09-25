"""PostToolUse hook: format, lint, and enforce AGENTS.md rules on edited Python files.

Runs after every Write/Edit. Steps:
1. `ruff check --fix` + `ruff format` on the edited file.
2. AST checks for the project rules in AGENTS.md.
3. Compares violations with the HEAD version of the file and reports only
   violations the edit introduced (ratchet), so legacy debt does not block work.

Exit code 2 feeds the report back to Claude. Also records the edited path so the
Stop hook knows Python changed during this session.

Can also run standalone for a full (non-ratcheted) audit:
    python .claude/hooks/check_rules.py --audit src/max_cli
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

HEAVY_PACKAGES = {
    "PIL",
    "fitz",
    "yt_dlp",
    "openai",
    "mutagen",
    "requests",
    "segno",
    "pyperclip",
}
TUI_ONLY_PACKAGES = {"textual", "psutil"}
ENGINE_CLASS_SUFFIXES = ("Engine", "Manager")
FFMPEG_BINARIES = {"ffmpeg", "ffprobe"}
TEXT_IO_METHODS = {"read_text", "write_text"}
# Receivers whose .open() is not a text file open (PDFs, images, archives, URLs).
NON_TEXT_OPENERS = {"fitz", "Image", "PIL.Image", "zipfile", "tarfile", "webbrowser"}
SILENT_BODY_TYPES = (ast.Pass, ast.Continue)
TYPE_IGNORE_BARE = re.compile(r"#\s*type:\s*ignore(\[[^\]]*\])?\s*$")
REPORT_LIMIT = 25


@dataclass(frozen=True)
class Violation:
    rule: str
    line: int
    message: str
    source_line: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.rule, self.source_line.strip())


class FileScope:
    """Which rule set applies, derived from the file's repo-relative path."""

    def __init__(self, rel_path: str) -> None:
        parts = Path(rel_path).parts
        self.is_src = parts[:2] == ("src", "max_cli")
        self.is_test = parts[:1] == ("tests",)
        pkg = parts[2:] if self.is_src else ()
        self.is_core_engine = pkg[:2] == ("core", "engines")
        self.is_common = pkg[:1] == ("common",)
        self.is_interface = pkg[:1] == ("interface",)
        self.is_tui = pkg[:2] == ("interface", "tui")
        self.is_cli_module = (
            self.is_interface and len(pkg) == 2 and pkg[1].startswith("cli_")
        )


class RuleVisitor(ast.NodeVisitor):
    def __init__(self, source: str, scope: FileScope) -> None:
        self.lines = source.splitlines()
        self.scope = scope
        self.violations: list[Violation] = []
        self.has_future_annotations = "from __future__ import annotations" in source
        self.imports_tarfile = re.search(
            r"^\s*import tarfile|^\s*from tarfile", source, re.M
        )
        self._depth = 0  # >0 inside def/class bodies
        self._type_checking_depth = 0

    def add(self, rule: str, node: ast.AST, message: str) -> None:
        line = getattr(node, "lineno", 1)
        text = self.lines[line - 1] if 0 < line <= len(self.lines) else ""
        self.violations.append(Violation(rule, line, message, text))

    # --- scope tracking -------------------------------------------------
    def _visit_scoped(self, node: ast.AST) -> None:
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_annotations(node)
        self._visit_scoped(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_annotations(node)
        self._visit_scoped(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_scoped(node)

    def visit_If(self, node: ast.If) -> None:
        test = ast.unparse(node.test)
        if test in ("TYPE_CHECKING", "typing.TYPE_CHECKING"):
            self._type_checking_depth += 1
            for child in node.body:
                self.visit(child)
            self._type_checking_depth -= 1
            for child in node.orelse:
                self.visit(child)
            return
        self.generic_visit(node)

    # --- imports --------------------------------------------------------
    def _check_import(self, node: ast.AST, module: str) -> None:
        top = module.split(".")[0]
        at_module_level = self._depth == 0 and self._type_checking_depth == 0
        if self.scope.is_src and at_module_level:
            heavy = top in HEAVY_PACKAGES or (
                top in TUI_ONLY_PACKAGES and not self.scope.is_tui
            )
            if heavy:
                self.add(
                    "lazy-import",
                    node,
                    f"Module-level import of heavy package '{top}'. "
                    "Move it inside the method that uses it.",
                )
        if (self.scope.is_core_engine or self.scope.is_common) and module.startswith(
            "max_cli.interface"
        ):
            self.add(
                "layering",
                node,
                "core/common must not import from max_cli.interface.",
            )
        if self.scope.is_core_engine and (
            top == "rich" or module == "max_cli.common.logger"
        ):
            self.add(
                "no-ui-in-core",
                node,
                "Engines must not import Rich/logger UI. Return data or emit events.",
            )

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_import(node, alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and node.level == 0:
            self._check_import(node, node.module)

    # --- module-level engine instantiation -------------------------------
    def visit_Assign(self, node: ast.Assign) -> None:
        if self.scope.is_cli_module and self._depth == 0:
            value = node.value
            if isinstance(value, ast.Call):
                name = ast.unparse(value.func).split(".")[-1]
                if name.endswith(ENGINE_CLASS_SUFFIXES):
                    self.add(
                        "engine-at-import",
                        node,
                        f"'{name}()' runs at import time. Use a _get_engine() helper.",
                    )
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._check_pep604(node.annotation, node)
        self.generic_visit(node)

    # --- calls ------------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        func = ast.unparse(node.func)
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}

        shell = kwargs.get("shell")
        if isinstance(shell, ast.Constant) and shell.value is True:
            self.add(
                "no-shell-true", node, "Never use shell=True. Pass an argument list."
            )

        if self.scope.is_core_engine and (func == "print" or func == "typer.echo"):
            self.add("no-print-in-core", node, "Engines must not print. Return values.")

        if self.scope.is_src:
            self._check_text_encoding(node, func, kwargs)
            if func.endswith(".write_text"):
                self.add(
                    "atomic-write",
                    node,
                    "Direct write_text can leave a truncated file on crash. Use "
                    "atomic_write_text/atomic_write_json from max_cli.common.atomic.",
                )
            if (
                func.endswith("extractall")
                and self.imports_tarfile
                and "filter" not in kwargs
            ):
                self.add(
                    "tar-filter",
                    node,
                    "tarfile.extractall without filter='data' allows path traversal.",
                )
        self.generic_visit(node)

    def _check_text_encoding(
        self, node: ast.Call, func: str, kwargs: dict[str, ast.expr]
    ) -> None:
        if "encoding" in kwargs:
            return
        method = func.split(".")[-1]
        if method in TEXT_IO_METHODS and "." in func:
            self.add("utf8", node, f"{method}() without encoding='utf-8'.")
            return
        if func not in ("open", "io.open") and not func.endswith(".open"):
            return
        if func.rsplit(".", 1)[0] in NON_TEXT_OPENERS:
            return
        mode_node = kwargs.get("mode")
        positional_mode_index = 1 if func in ("open", "io.open") else 0
        if mode_node is None and len(node.args) > positional_mode_index:
            mode_node = node.args[positional_mode_index]
        if mode_node is None:
            mode = "r"
        elif isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
            mode = mode_node.value
        else:
            return
        if "b" not in mode:
            self.add("utf8", node, "Text-mode open() without encoding='utf-8'.")

    # --- attributes / constants -------------------------------------------
    def visit_Attribute(self, node: ast.Attribute) -> None:
        if (
            self.scope.is_src
            and node.attr == "path"
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
        ):
            self.add("pathlib", node, "os.path is banned. Use pathlib.Path.")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and (
            node.value == "/tmp" or node.value.startswith("/tmp/")
        ):
            self.add("no-tmp", node, "Hardcoded /tmp. Use tempfile or ~/.max_cli.")

    def visit_List(self, node: ast.List) -> None:
        if (
            self.scope.is_src
            and node.elts
            and isinstance(node.elts[0], ast.Constant)
            and node.elts[0].value in FFMPEG_BINARIES
        ):
            self.add(
                "ffmpeg-path",
                node,
                "Hardcoded ffmpeg/ffprobe binary. Use str(self.ffmpeg_path).",
            )
        self.generic_visit(node)

    # --- exceptions ---------------------------------------------------------
    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self.add("bare-except", node, "Bare 'except:'. Catch specific exceptions.")
        else:
            caught = ast.unparse(node.type)
            is_broad = caught in ("Exception", "BaseException")
            is_silent = all(
                isinstance(stmt, SILENT_BODY_TYPES)
                or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
                for stmt in node.body
            )
            if is_broad and is_silent:
                self.add(
                    "silent-except",
                    node,
                    f"'except {caught}' that swallows the error. "
                    "Catch specific exceptions or log with log_error.",
                )
        self.generic_visit(node)

    # --- Python 3.9 compatibility -------------------------------------------
    def _check_annotations(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        all_args = node.args.args + node.args.kwonlyargs + node.args.posonlyargs
        for extra in (node.args.vararg, node.args.kwarg):
            if extra is not None:
                all_args.append(extra)
        for arg in all_args:
            if arg.annotation is not None:
                self._check_pep604(arg.annotation, arg)
        if node.returns is not None:
            self._check_pep604(node.returns, node)

    def _check_pep604(self, annotation: ast.expr, anchor: ast.AST) -> None:
        if self.has_future_annotations:
            return
        if isinstance(annotation, ast.Constant):  # string annotation, not evaluated
            return
        for sub in ast.walk(annotation):
            if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr):
                self.add(
                    "py39-union",
                    anchor,
                    "'X | Y' annotation crashes on Python 3.9. Use Optional/Union "
                    "or add 'from __future__ import annotations'.",
                )
                return

    def visit_Match(self, node: ast.AST) -> None:
        self.add("py39-match", node, "'match' statement requires Python 3.10+.")
        self.generic_visit(node)


def find_violations(source: str, rel_path: str) -> list[Violation]:
    scope = FileScope(rel_path)
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [Violation("syntax", exc.lineno or 1, f"SyntaxError: {exc.msg}", "")]
    visitor = RuleVisitor(source, scope)
    visitor.visit(tree)
    for index, line in enumerate(visitor.lines, start=1):
        if TYPE_IGNORE_BARE.search(line):
            visitor.violations.append(
                Violation(
                    "type-ignore-reason",
                    index,
                    "'# type: ignore' needs a short reason comment after it.",
                    line,
                )
            )
    return visitor.violations


def git_head_source(repo_root: Path, rel_path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"HEAD:{rel_path}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout if result.returncode == 0 else None


def introduced_violations(
    current: list[Violation], baseline: list[Violation]
) -> list[Violation]:
    remaining = Counter(v.key for v in baseline)
    new: list[Violation] = []
    for violation in current:
        if remaining[violation.key] > 0:
            remaining[violation.key] -= 1
        else:
            new.append(violation)
    return new


def head_was_formatted(repo_root: Path, rel_path: str, head_source: str) -> bool:
    check = subprocess.run(
        ["ruff", "format", "--check", "--quiet", "--stdin-filename", rel_path, "-"],
        cwd=repo_root,
        input=head_source,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return check.returncode == 0


def run_ruff(
    repo_root: Path, file_path: Path, rel_path: str, head_source: str | None
) -> str:
    """Autofix + format, then return any remaining lint errors.

    Formats only new files or files already formatted at HEAD, so touching a
    legacy file does not bury the real change under a whole-file reformat.
    """
    try:
        subprocess.run(
            # F401 stays unfixable: an import added before the code that uses it
            # (multi-step edits) must not be deleted as "unused" in between.
            [
                "ruff",
                "check",
                "--fix",
                "--unfixable",
                "F401",
                "--quiet",
                str(file_path),
            ],
            cwd=repo_root,
            capture_output=True,
        )
        if head_source is None or head_was_formatted(repo_root, rel_path, head_source):
            subprocess.run(
                ["ruff", "format", "--quiet", str(file_path)],
                cwd=repo_root,
                capture_output=True,
            )
        remaining = subprocess.run(
            ["ruff", "check", "--output-format", "concise", str(file_path)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return ""
    return remaining.stdout.strip() if remaining.returncode != 0 else ""


def record_edit(repo_root: Path, session_id: str, rel_path: str) -> None:
    state_dir = repo_root / ".claude" / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)
    marker = state_dir / f"{session_id or 'default'}.edited"
    with marker.open("a", encoding="utf-8") as handle:
        handle.write(rel_path + "\n")


def format_report(rel_path: str, violations: list[Violation]) -> str:
    shown = violations[:REPORT_LIMIT]
    lines = [f"{rel_path}:{v.line}: [{v.rule}] {v.message}" for v in shown]
    if len(violations) > REPORT_LIMIT:
        lines.append(f"... and {len(violations) - REPORT_LIMIT} more")
    return "\n".join(lines)


def hook_main() -> int:
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input") or {}
    raw_path = tool_input.get("file_path") or ""
    if not raw_path.endswith(".py"):
        return 0

    repo_root = Path(payload.get("cwd") or ".").resolve()
    file_path = Path(raw_path).resolve()
    try:
        rel_path = file_path.relative_to(repo_root).as_posix()
    except ValueError:
        return 0
    scope = FileScope(rel_path)
    if not (scope.is_src or scope.is_test) or not file_path.exists():
        return 0

    record_edit(repo_root, payload.get("session_id", ""), rel_path)

    head_source = git_head_source(repo_root, rel_path)
    ruff_errors = run_ruff(repo_root, file_path, rel_path, head_source)
    source = file_path.read_text(encoding="utf-8")
    current = find_violations(source, rel_path)
    baseline = find_violations(head_source, rel_path) if head_source else []
    new_violations = introduced_violations(current, baseline)

    if not new_violations and not ruff_errors:
        return 0

    sections = []
    if new_violations:
        sections.append(
            "AGENTS.md rule violations introduced by this edit "
            "(fix them before continuing):\n" + format_report(rel_path, new_violations)
        )
    if ruff_errors:
        sections.append("Ruff errors ruff --fix could not repair:\n" + ruff_errors)
    print("\n\n".join(sections), file=sys.stderr)
    return 2


def audit_main(targets: list[str]) -> int:
    repo_root = Path.cwd().resolve()
    rule_counts: Counter[str] = Counter()
    for target in targets:
        root = Path(target)
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for file_path in files:
            rel_path = file_path.resolve().relative_to(repo_root).as_posix()
            violations = find_violations(
                file_path.read_text(encoding="utf-8"), rel_path
            )
            if violations:
                print(format_report(rel_path, violations))
                rule_counts.update(v.rule for v in violations)
    print("\nViolations by rule:")
    for rule, count in rule_counts.most_common():
        print(f"  {rule}: {count}")
    print(f"Total: {sum(rule_counts.values())}")
    return 1 if rule_counts else 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--audit":
        sys.exit(audit_main(sys.argv[2:] or ["src/max_cli"]))
    sys.exit(hook_main())
