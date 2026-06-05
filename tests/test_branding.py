import re
from pathlib import Path

from opennego.branding import CLI_NAME, PRODUCT_NAME, TECHNICAL_HANDLE


def test_public_branding_constants_are_explicit():
    assert PRODUCT_NAME == "OpenNegotiation"
    assert TECHNICAL_HANDLE == "OpenNego"
    assert CLI_NAME == "opennego"


def test_legacy_handle_only_appears_in_allowed_technical_contexts():
    allowed = {
        "README.md": ("Kordi-AI/OpenNego", "cd OpenNego"),
        "docs/naming.md": ("OpenNego",),
        "src/opennego/branding.py": ("OpenNego",),
        "tests/test_branding.py": ("OpenNego",),
    }
    roots = ("README.md", "docs", "src", "examples", "tests", "configs")
    violations = []
    for root in roots:
        path = Path(root)
        files = [path] if path.is_file() else path.rglob("*")
        for file_path in files:
            if (
                not file_path.is_file()
                or file_path.suffix in {".pyc", ".png"}
                or "opennego.egg-info" in file_path.parts
            ):
                continue
            text = file_path.read_text(errors="ignore")
            if not re.search(r"\bOpenNego\b", text):
                continue
            allowed_fragments = allowed.get(str(file_path), ())
            remainder = text
            for fragment in allowed_fragments:
                remainder = remainder.replace(fragment, "")
            if re.search(r"\bOpenNego\b", remainder):
                violations.append(str(file_path))
    assert violations == []
