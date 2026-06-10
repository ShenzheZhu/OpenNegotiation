import json

from opennego.model_demo import run_model_demo
from opennego.ports import LLMRequest, LLMResponse
from opennego.report import write_demo_report
from opennego.cli.common import llm_preflight_error


class FakeModelDemoLLM:
    def __init__(self):
        self.responses = [
            (
                '{"type": "tool_call", "tool": {"name": "market_price_search", '
                '"arguments": {"query": "Apple iPhone 14 Pro 128GB Unlocked", '
                '"condition": "used_good", "limit": 3}}}'
            ),
            '{"type": "offer", "price": 560, "note": "Market-backed offer."}',
        ]

    def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            model=request.model,
            content=self.responses.pop(0),
        )


class FailingModelDemoLLM:
    def complete(self, request: LLMRequest) -> LLMResponse:
        raise RuntimeError("provider rejected key " + "s" "k-or-v1-do-not-store")


class MixedModelDemoLLM:
    def __init__(self):
        self.success = FakeModelDemoLLM()

    def complete(self, request: LLMRequest) -> LLMResponse:
        if "failing" in request.model:
            raise RuntimeError("provider unavailable")
        return self.success.complete(request)


def test_model_demo_writes_artifacts_and_report_with_fake_llm(tmp_path):
    output_dir = tmp_path / "model-runs"
    summary = run_model_demo(
        models=("fake/model-a", "fake/model-b"),
        output_dir=output_dir,
        llm_factory=FakeModelDemoLLM,
    )
    report_path = write_demo_report(output_dir, tmp_path / "report.html")

    html = report_path.read_text()
    assert summary.total_runs == 2
    assert summary.completed == 2
    assert summary.failed == 0
    assert "fake/model-a" in html
    assert "fake/model-b" in html
    assert "Leaderboard Preview" in html


def test_model_demo_writes_redacted_failure_artifacts(tmp_path):
    output_dir = tmp_path / "model-runs"
    summary = run_model_demo(
        models=("fake/failing-model",),
        output_dir=output_dir,
        llm_factory=FailingModelDemoLLM,
    )

    failure_path = output_dir / "five_model_demo-fake-failing-model" / "failure.json"
    summary_path = output_dir / "summary.json"
    failure = json.loads(failure_path.read_text())
    summary_payload = json.loads(summary_path.read_text())

    assert summary.total_runs == 1
    assert summary.completed == 0
    assert summary.failed == 1
    assert failure["status"] == "failed"
    assert failure["error_type"] == "RuntimeError"
    assert "[redacted-secret]" in failure["error"]
    assert "s" "k-or-v1" not in failure_path.read_text()
    assert summary_payload["schema_version"] == "opennego.model_demo.v1"
    assert summary_payload["runs"][0]["failure_path"] == str(failure_path)


def test_model_demo_report_shows_attempt_status_for_failures(tmp_path):
    output_dir = tmp_path / "model-runs"
    run_model_demo(
        models=("fake/model-a", "fake/failing-model"),
        output_dir=output_dir,
        llm_factory=MixedModelDemoLLM,
    )
    report_path = write_demo_report(output_dir, tmp_path / "report.html")

    html = report_path.read_text()
    assert "Leaderboard Preview" in html
    assert "Run Attempt Status" in html
    assert 'href="#attempts"' in html
    assert "fake/model-a" in html
    assert "fake/failing-model" in html
    assert "RuntimeError: provider unavailable" in html


def test_run_models_preflight_reports_missing_litellm(monkeypatch):
    monkeypatch.setattr("opennego.cli.common.importlib.util.find_spec", lambda name: None)

    error = llm_preflight_error(("openrouter/openai/gpt-4o-mini",))

    assert error is not None
    assert "LiteLLM is not installed" in error


def test_run_models_preflight_reports_missing_openrouter_key(monkeypatch):
    monkeypatch.setattr("opennego.cli.common.importlib.util.find_spec", lambda name: object())
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    error = llm_preflight_error(("openrouter/openai/gpt-4o-mini",))

    assert error == "Missing provider environment variable(s): OPENROUTER_API_KEY"
