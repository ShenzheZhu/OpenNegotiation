import re
from pathlib import Path

from opennego.branding import CLI_NAME, PRODUCT_NAME, TECHNICAL_HANDLE


def test_public_branding_constants_are_explicit():
    assert PRODUCT_NAME == "OpenNegotiation"
    assert TECHNICAL_HANDLE == "OpenNegotiation"
    assert CLI_NAME == "opennego"


def test_legacy_camelcase_handle_is_removed_from_repo_copy():
    legacy_handle = "Open" + "Nego"
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
            if re.search(rf"\b{legacy_handle}\b", text):
                violations.append(str(file_path))
    assert violations == []
