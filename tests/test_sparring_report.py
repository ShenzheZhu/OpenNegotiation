import json

from opennego.cli import main
from opennego.sparring import run_sparring_suite
from opennego.sparring_report import write_sparring_report


def test_write_sparring_report_renders_profile_lessons(tmp_path):
    output_dir = tmp_path / "sparring"
    report_path = tmp_path / "sparring.html"
    summary = run_sparring_suite(
        output_dir=output_dir,
        opponent_profile_ids=("seller_hardline_anchor_v1",),
    )

    written = write_sparring_report(summary.artifact_path, report_path)
    html = written.read_text()

    assert written == report_path
    assert "OpenNegotiation strategy sparring report" in html
    assert "profile_backed_fixture_sparring" in html
    assert "Hardline Anchor Seller" in html
    assert "buyer_overpaid_market" in html
    assert not any(line.rstrip() != line for line in html.splitlines())


def test_spar_cli_can_write_html_report(tmp_path, capsys):
    output_dir = tmp_path / "sparring"
    report_path = tmp_path / "sparring.html"

    status = main(
        [
            "spar",
            "--output-dir",
            str(output_dir),
            "--opponent-profile",
            "seller_hardline_anchor_v1",
            "--report",
            str(report_path),
        ]
    )
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)

    assert status == 0
    assert payload["html_report"] == str(report_path)
    assert report_path.exists()
    assert "Hardline Anchor Seller" in report_path.read_text()
