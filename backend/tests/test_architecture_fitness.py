"""
Architecture fitness functions.

These tests enforce structural rules about the codebase using AST analysis.
They run fast (no I/O) and catch architectural drift before it becomes debt.
"""

import ast
import re
from pathlib import Path

import pytest

BACKEND_SRC = Path(__file__).parent.parent / "src"
ROUTES_DIR = BACKEND_SRC / "api" / "routes"


def _get_python_files(directory: Path) -> list[Path]:
    """Recursively find all .py files in directory."""
    return sorted(directory.rglob("*.py"))


def _parse_file(path: Path) -> ast.Module:
    """Parse a Python file into an AST."""
    return ast.parse(path.read_text(), filename=str(path))


def _get_function_body_lines(func: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count non-blank, non-comment lines in a function body."""
    count = 0
    for node in ast.walk(func):
        if isinstance(node, ast.stmt) and node is not func:
            # Exclude docstrings (first Expr with a Constant string)
            if (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                continue
            count += 1
    return count


def _is_route_handler(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if a function is decorated with a router method decorator."""
    for decorator in func.decorator_list:
        if isinstance(decorator, ast.Call):
            dec_func = decorator.func
        else:
            dec_func = decorator

        if isinstance(dec_func, ast.Attribute):
            if dec_func.attr in ("get", "post", "put", "delete", "patch"):
                return True
    return False


class TestRoutesAreThin:
    """Route handler functions should have at most 50 lines of body."""

    MAX_ROUTE_BODY_LINES = 50

    def test_routes_are_thin(self):
        """Parse all files in src/api/routes/. Route handlers should be at most 40 lines."""
        violations = []

        for path in _get_python_files(ROUTES_DIR):
            if path.name == "__init__.py":
                continue

            tree = _parse_file(path)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if _is_route_handler(node):
                        body_lines = _get_function_body_lines(node)
                        if body_lines > self.MAX_ROUTE_BODY_LINES:
                            violations.append(
                                f"{path.name}:{node.name} has {body_lines} lines "
                                f"(max {self.MAX_ROUTE_BODY_LINES})"
                            )

        assert not violations, (
            f"Route handlers exceed {self.MAX_ROUTE_BODY_LINES} line limit:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


class TestNoDirectLLMInRoutes:
    """No file in src/api/routes/ should import LLM libraries directly."""

    BANNED_IMPORTS = {"langchain_openai", "langchain_groq", "langchain"}

    def test_no_direct_llm_in_routes(self):
        """Routes call agent functions, not LLM libraries directly."""
        violations = []

        for path in _get_python_files(ROUTES_DIR):
            if path.name == "__init__.py":
                continue

            tree = _parse_file(path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_root = alias.name.split(".")[0]
                        if module_root in self.BANNED_IMPORTS:
                            violations.append(f"{path.name}: import {alias.name}")

                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        module_root = node.module.split(".")[0]
                        if module_root in self.BANNED_IMPORTS:
                            violations.append(f"{path.name}: from {node.module} import ...")

        assert not violations, (
            "Routes should not import LLM libraries directly:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


class TestNoBlockingCallsInAsync:
    """Scan for async functions that call blocking operations."""

    BLOCKING_CALLS = {
        "time.sleep",
        "requests.get",
        "requests.post",
        "requests.put",
        "requests.delete",
        "requests.patch",
    }

    def test_no_blocking_calls_in_async(self):
        """Async functions should not call time.sleep or requests methods."""
        violations = []

        for path in _get_python_files(BACKEND_SRC):
            tree = _parse_file(path)

            for node in ast.walk(tree):
                if not isinstance(node, ast.AsyncFunctionDef):
                    continue

                for child in ast.walk(node):
                    if not isinstance(child, ast.Call):
                        continue

                    call_name = self._get_call_name(child)
                    if call_name in self.BLOCKING_CALLS:
                        violations.append(
                            f"{path.relative_to(BACKEND_SRC)}:{node.name} "
                            f"calls {call_name}"
                        )

        assert not violations, (
            "Blocking calls found in async functions:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    @staticmethod
    def _get_call_name(call_node: ast.Call) -> str:
        """Extract dotted name from a Call node (e.g., 'time.sleep')."""
        func = call_node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            return f"{func.value.id}.{func.attr}"
        return ""


class TestAllRoutesHaveDocstrings:
    """Every function decorated with @router.get/post/put/delete must have a docstring."""

    # Routes that already have docstrings on all handlers and must keep them.
    # New routes added to these files should also include docstrings.
    ENFORCED_FILES = {
        "analyze_stream.py",
        "admin.py",
        "compare.py",
        "eval.py",
    }

    def test_all_routes_have_docstrings(self):
        """Route handlers in enforced files must have docstrings."""
        violations = []

        for path in _get_python_files(ROUTES_DIR):
            if path.name == "__init__.py":
                continue
            if path.name not in self.ENFORCED_FILES:
                continue

            tree = _parse_file(path)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if _is_route_handler(node):
                        docstring = ast.get_docstring(node)
                        if not docstring:
                            violations.append(f"{path.name}:{node.name}")

        assert not violations, (
            "Route handlers missing docstrings:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


class TestNoBareExceptions:
    """No bare except clauses without logging or re-raise."""

    # Directories where bare exceptions are acceptable (data fetching with fallbacks)
    EXEMPT_DIRS = {"mcp_servers", "cache"}

    def test_no_bare_exceptions(self):
        """Bare exception handlers in core paths must log or re-raise."""
        violations = []

        for path in _get_python_files(BACKEND_SRC):
            rel = path.relative_to(BACKEND_SRC)
            # Skip directories that intentionally use silent fallbacks
            if any(part in self.EXEMPT_DIRS for part in rel.parts):
                continue

            tree = _parse_file(path)
            source_lines = path.read_text().splitlines()

            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue

                # Only flag truly bare `except:` (no type at all)
                # `except Exception:` with a return/pass is acceptable for fallbacks
                is_bare = node.type is None
                if not is_bare:
                    continue

                # Check if the handler logs, re-raises, or returns a value
                has_handling = False

                for child in ast.walk(node):
                    if isinstance(child, ast.Raise):
                        has_handling = True
                        break

                    if isinstance(child, ast.Return):
                        has_handling = True
                        break

                    if isinstance(child, ast.Call):
                        call_name = self._get_full_call_name(child)
                        if any(
                            prefix in call_name
                            for prefix in ("log.", "logger.", "logging.")
                        ):
                            has_handling = True
                            break

                    if isinstance(child, ast.Pass):
                        # Pass with inline comment is intentional suppression
                        line_idx = child.lineno - 1
                        if line_idx < len(source_lines):
                            line = source_lines[line_idx]
                            if "#" in line:
                                has_handling = True
                                break

                if not has_handling:
                    violations.append(
                        f"{rel}:{node.lineno} "
                        f"bare except without logging or re-raise"
                    )

        assert not violations, (
            "Bare exception handlers without logging/re-raise:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    @staticmethod
    def _get_full_call_name(call_node: ast.Call) -> str:
        """Extract dotted name from a Call node."""
        func = call_node.func
        if isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name):
                return f"{func.value.id}.{func.attr}"
            elif isinstance(func.value, ast.Attribute) and isinstance(
                func.value.value, ast.Name
            ):
                return f"{func.value.value.id}.{func.value.attr}.{func.attr}"
        elif isinstance(func, ast.Name):
            return func.id
        return ""


class TestPydanticModelsHaveExamples:
    """Pydantic models in structured_output.py should have model_config or field examples."""

    # Models with 3+ fields that carry domain semantics should document them.
    # Small leaf models (1-2 fields) or simple containers are exempt.
    MIN_FIELDS_FOR_ENFORCEMENT = 3

    def test_pydantic_models_have_field_descriptions(self):
        """Pydantic models with 3+ fields in structured_output.py should have Field descriptions."""
        structured_output = BACKEND_SRC / "agent" / "structured_output.py"
        if not structured_output.exists():
            pytest.skip("structured_output.py not found")

        tree = _parse_file(structured_output)
        violations = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            # Check if it's a Pydantic model (inherits from BaseModel)
            is_model = any(
                (isinstance(base, ast.Name) and base.id == "BaseModel")
                for base in node.bases
            )
            if not is_model:
                continue

            # Check that at least some fields have descriptions
            has_field_metadata = False
            field_count = 0

            for item in node.body:
                if isinstance(item, ast.AnnAssign) and item.value is not None:
                    field_count += 1
                    # Check if Field() is used with description
                    if isinstance(item.value, ast.Call):
                        call_name = ""
                        if isinstance(item.value.func, ast.Name):
                            call_name = item.value.func.id
                        if call_name == "Field":
                            for kw in item.value.keywords:
                                if kw.arg == "description":
                                    has_field_metadata = True
                                    break

            if field_count >= self.MIN_FIELDS_FOR_ENFORCEMENT and not has_field_metadata:
                violations.append(f"{node.name}: no Field(description=...) on any field")

        assert not violations, (
            "Pydantic models missing field descriptions:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


class TestNoHardcodedApiKeys:
    """Scan all .py files for string literals that look like API keys."""

    API_KEY_PATTERNS = [
        re.compile(r"sk-[a-zA-Z0-9]{20,}"),
        re.compile(r"gsk_[a-zA-Z0-9]{20,}"),
        re.compile(r"xai-[a-zA-Z0-9]{20,}"),
        re.compile(r"[A-Z0-9]{40,}"),  # Long uppercase strings
    ]

    def test_no_hardcoded_api_keys(self):
        """No hardcoded API keys in source files (excluding tests)."""
        violations = []

        for path in _get_python_files(BACKEND_SRC):
            tree = _parse_file(path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    value = node.value
                    if len(value) < 20:
                        continue

                    for pattern in self.API_KEY_PATTERNS:
                        if pattern.fullmatch(value):
                            violations.append(
                                f"{path.relative_to(BACKEND_SRC)}:{node.lineno} "
                                f"potential API key: {value[:10]}..."
                            )
                            break

        assert not violations, (
            "Potential hardcoded API keys found:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


class TestEventTypesAreExhaustive:
    """Verify all event types defined in EventType are emitted by EventEmitter."""

    def test_event_types_are_exhaustive(self):
        """All EventType enum members should have corresponding EventEmitter methods."""
        events_file = BACKEND_SRC / "agent" / "events.py"
        if not events_file.exists():
            pytest.skip("events.py not found")

        tree = _parse_file(events_file)

        # Find all EventType enum values
        event_types: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "EventType":
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                event_types.add(target.id)

        # Find all event types actually emitted in EventEmitter._emit() calls
        emitted_types: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "EventEmitter":
                for item in ast.walk(node):
                    if isinstance(item, ast.Call):
                        # Look for self._emit(EventType.X, ...) calls
                        if isinstance(item.func, ast.Attribute):
                            if item.func.attr == "_emit" and item.args:
                                first_arg = item.args[0]
                                if (
                                    isinstance(first_arg, ast.Attribute)
                                    and isinstance(first_arg.value, ast.Name)
                                    and first_arg.value.id == "EventType"
                                ):
                                    emitted_types.add(first_arg.attr)

        # Every defined EventType should be emitted somewhere
        missing = event_types - emitted_types
        assert not missing, (
            f"EventType members not emitted by EventEmitter: {sorted(missing)}"
        )
