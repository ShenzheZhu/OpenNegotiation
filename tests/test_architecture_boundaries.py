import ast
from pathlib import Path


PROVIDER_IMPORTS = {
    "litellm",
    "openai",
    "anthropic",
    "google.generativeai",
}

ADAPTER_IMPORTS = {
    "opennego.adapters",
}

ALLOWED_PROVIDER_FILES = {
    Path("src/opennego/adapters/__init__.py"),
    Path("src/opennego/adapters/litellm_gateway.py"),
    Path("src/opennego/adapters/ebay_browse.py"),
    Path("src/opennego/model_demo.py"),
}


def test_provider_specific_imports_stay_out_of_core_modules():
    repo_root = Path(__file__).resolve().parents[1]
    for path in sorted((repo_root / "src/opennego").rglob("*.py")):
        relative = path.relative_to(repo_root)
        if relative in ALLOWED_PROVIDER_FILES:
            continue

        tree = ast.parse(path.read_text(), filename=str(relative))
        imports = _imports(tree)
        forbidden = [
            name
            for name in imports
            if _matches_any(name, PROVIDER_IMPORTS | ADAPTER_IMPORTS)
        ]
        assert forbidden == [], (
            f"{relative} imports provider-specific modules: {forbidden}"
        )


def test_declared_python_runtime_matches_current_syntax():
    repo_root = Path(__file__).resolve().parents[1]
    pyproject = (repo_root / "pyproject.toml").read_text()
    assert 'requires-python = ">=3.10"' in pyproject


def _imports(tree: ast.AST) -> list[str]:
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _matches_any(name: str, prefixes: set[str]) -> bool:
    return any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes)
