from pathlib import Path


def test_market_ingestion_workflow_is_scheduled_and_secret_backed():
    workflow = Path(".github/workflows/market-ingestion.yml").read_text()

    assert "workflow_dispatch:" in workflow
    assert "schedule:" in workflow
    assert 'cron: "0 9 * * 1"' in workflow
    assert "EBAY_CLIENT_ID: ${{ secrets.EBAY_CLIENT_ID }}" in workflow
    assert "EBAY_CLIENT_SECRET: ${{ secrets.EBAY_CLIENT_SECRET }}" in workflow
    assert "opennego ingest-ebay" in workflow
    assert "opennego validate-market" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "--mock-response" not in workflow
    assert "fixture" not in workflow.lower()
