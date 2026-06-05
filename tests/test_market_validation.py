import csv
import json

from opennego.cli import main
from opennego.market_ingestion import ingest_market_data
from opennego.market_validation import (
    MARKET_VALIDATION_SCHEMA_VERSION,
    validate_market_dataset,
)


def test_validate_market_dataset_accepts_generated_manifest(tmp_path):
    paths = _write_ingested_dataset(tmp_path)

    result = validate_market_dataset(
        products_file=paths["products"],
        market_comps_file=paths["comps"],
        manifest_file=paths["manifest"],
    )

    assert result.schema_version == MARKET_VALIDATION_SCHEMA_VERSION
    assert result.status == "passed"
    assert result.product_count == 1
    assert result.comparable_count == 3
    assert result.errors == ()


def test_validate_market_dataset_reports_manifest_count_and_median_mismatch(tmp_path):
    paths = _write_ingested_dataset(tmp_path)
    manifest = json.loads(paths["manifest"].read_text())
    manifest["comparable_count"] = 999
    manifest["quality"]["price_summary"]["median"] = 999.0
    paths["manifest"].write_text(json.dumps(manifest, indent=2) + "\n")

    result = validate_market_dataset(
        products_file=paths["products"],
        market_comps_file=paths["comps"],
        manifest_file=paths["manifest"],
    )

    assert result.status == "failed"
    assert "manifest.comparable_count: expected 3, got 999" in result.errors
    assert (
        "manifest.quality.price_summary.median: expected 575.0, got 999.0"
        in result.errors
    )


def test_validate_market_dataset_warns_when_manifest_input_is_unavailable(tmp_path):
    paths = _write_ingested_dataset(tmp_path)
    paths["input"].unlink()

    result = validate_market_dataset(
        products_file=paths["products"],
        market_comps_file=paths["comps"],
        manifest_file=paths["manifest"],
    )

    assert result.status == "passed"
    assert any("sha256 not rechecked" in warning for warning in result.warnings)


def test_validate_market_cli_uses_exit_code_for_dataset_status(tmp_path, capsys):
    paths = _write_ingested_dataset(tmp_path)

    pass_code = main(
        [
            "validate-market",
            "--products-file",
            str(paths["products"]),
            "--market-comps-file",
            str(paths["comps"]),
            "--manifest-file",
            str(paths["manifest"]),
        ]
    )
    pass_payload = json.loads(capsys.readouterr().out)

    manifest = json.loads(paths["manifest"].read_text())
    manifest["product_count"] = 99
    paths["manifest"].write_text(json.dumps(manifest, indent=2) + "\n")
    fail_code = main(
        [
            "validate-market",
            "--products-file",
            str(paths["products"]),
            "--market-comps-file",
            str(paths["comps"]),
            "--manifest-file",
            str(paths["manifest"]),
        ]
    )
    fail_payload = json.loads(capsys.readouterr().out)

    assert pass_code == 0
    assert pass_payload["status"] == "passed"
    assert fail_code == 1
    assert fail_payload["status"] == "failed"
    assert "manifest.product_count: expected 1, got 99" in fail_payload["errors"]


def _write_ingested_dataset(tmp_path):
    input_path = tmp_path / "sold_comps.csv"
    products_path = tmp_path / "products.json"
    comps_path = tmp_path / "market_comps.json"
    manifest_path = tmp_path / "market_dataset.json"
    _write_csv(
        input_path,
        [
            {
                "product_name": "Apple iPhone 14 Pro 128GB Unlocked",
                "listing_title": "iPhone 14 Pro clean IMEI",
                "sold_price": "$555.00",
                "condition": "used_good",
                "marketplace": "ebay_offline_export",
                "format": "best_offer",
                "currency": "USD",
                "sold_at": "2026-05-01",
            },
            {
                "product_name": "Apple iPhone 14 Pro 128GB Unlocked",
                "listing_title": "Unlocked iPhone 14 Pro",
                "sold_price": "575",
                "condition": "used_good",
                "marketplace": "ebay_offline_export",
                "format": "buy_it_now",
                "currency": "USD",
                "sold_at": "2026-05-03",
            },
            {
                "product_name": "Apple iPhone 14 Pro 128GB Unlocked",
                "listing_title": "iPhone 14 Pro 128GB",
                "sold_price": "610",
                "condition": "used_good",
                "marketplace": "ebay_offline_export",
                "format": "buy_it_now",
                "currency": "USD",
                "sold_at": "2026-05-06",
            },
        ],
    )
    ingest_market_data(
        input_path=input_path,
        products_output=products_path,
        comps_output=comps_path,
        manifest_output=manifest_path,
        source="ebay_offline_export",
        window_days=90,
    )
    return {
        "input": input_path,
        "products": products_path,
        "comps": comps_path,
        "manifest": manifest_path,
    }


def _write_csv(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
