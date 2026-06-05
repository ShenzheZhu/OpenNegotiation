import csv
import hashlib
import json

from opennego.cli import main
from opennego.market_ingestion import (
    MARKET_DATASET_MANIFEST_SCHEMA_VERSION,
    ingest_market_data,
)
from opennego.market_sources import write_market_source_policy
from opennego.schema import Product
from opennego.tools import MarketPriceTool


def test_ingest_market_data_from_csv_writes_products_and_comps(tmp_path):
    input_path = tmp_path / "sold_comps.csv"
    products_path = tmp_path / "products.json"
    comps_path = tmp_path / "market_comps.json"
    manifest_path = tmp_path / "dataset_manifest.json"
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

    result = ingest_market_data(
        input_path=input_path,
        products_output=products_path,
        comps_output=comps_path,
        source="ebay_sold_offline",
        window_days=90,
        manifest_output=manifest_path,
    )
    products = json.loads(products_path.read_text())
    comps = json.loads(comps_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    product = Product.from_mapping(products[0])
    tool = MarketPriceTool.from_json(comps_path)
    tool_result = tool.call(
        {
            "query": "Apple iPhone 14 Pro 128GB Unlocked",
            "condition": "used_good",
            "limit": 5,
        },
        context=None,
    )

    assert result.product_count == 1
    assert result.comparable_count == 3
    assert result.manifest_output == str(manifest_path)
    assert product.market_reference is not None
    assert product.market_reference.reference_price == 575.0
    assert product.market_reference.p25_price == 565.0
    assert product.market_reference.p75_price == 592.5
    assert product.market_reference.sample_size == 3
    assert product.market_reference.window_days == 90
    assert product.market_reference.source == "ebay_sold_offline"
    assert product.market_reference.sale_mechanism == "mixed"
    assert product.market_reference.metadata["schema_version"] == (
        "opennego.market_ingestion.v1"
    )
    assert products[0]["synthetic_seller_reservation_price"] == 565.0
    assert products[0]["asking_price"] == 718.75
    assert comps[0]["source"] == "ebay_offline_export"
    assert comps[0]["sold_at"] == "2026-05-01"
    assert tool_result["count"] == 3
    assert tool_result["median_price"] == 575.0
    assert manifest["schema_version"] == MARKET_DATASET_MANIFEST_SCHEMA_VERSION
    assert manifest["input"]["sha256"] == hashlib.sha256(
        input_path.read_bytes()
    ).hexdigest()
    assert manifest["input"]["format"] == "csv"
    assert manifest["outputs"]["products"] == str(products_path)
    assert manifest["outputs"]["market_comps"] == str(comps_path)
    assert manifest["product_count"] == 1
    assert manifest["comparable_count"] == 3
    assert manifest["quality"]["missing_sold_at_count"] == 0
    assert manifest["quality"]["price_summary"] == {
        "count": 3,
        "min": 555.0,
        "p25": 565.0,
        "median": 575.0,
        "p75": 592.5,
        "max": 610.0,
    }
    assert manifest["quality"]["counts_by_source"] == {"ebay_offline_export": 3}
    assert manifest["quality"]["counts_by_sale_mechanism"] == {
        "best_offer": 1,
        "buy_it_now": 2,
    }
    assert manifest["quality"]["clusters"][0]["product_id"] == (
        "apple-iphone-14-pro-128gb-unlocked"
    )
    assert manifest["quality"]["clusters"][0]["sample_size"] == 3
    assert manifest["privacy"] == {
        "contains_credentials": False,
        "contains_raw_listing_titles": False,
    }
    assert "iPhone 14 Pro clean IMEI" not in json.dumps(manifest)


def test_ingest_market_data_from_json_groups_multiple_products(tmp_path):
    input_path = tmp_path / "sold_comps.json"
    products_path = tmp_path / "products.json"
    comps_path = tmp_path / "market_comps.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "query": "Sony a6400 body",
                    "title": "Sony a6400 lightly used",
                    "price": 800,
                    "condition": "used",
                },
                {
                    "query": "Sony a6400 body",
                    "title": "Sony Alpha a6400",
                    "price": 820,
                    "condition": "used",
                },
                {
                    "query": "Nintendo Switch OLED",
                    "title": "Switch OLED console",
                    "price": 260,
                    "condition": "used_good",
                },
            ],
            indent=2,
        )
        + "\n"
    )

    result = ingest_market_data(
        input_path=input_path,
        products_output=products_path,
        comps_output=comps_path,
        source="offline_json",
    )
    products = json.loads(products_path.read_text())

    assert result.product_count == 2
    assert result.comparable_count == 3
    assert [item["name"] for item in products] == [
        "Nintendo Switch OLED",
        "Sony a6400 body",
    ]
    assert products[1]["market_reference"]["reference_price"] == 810.0
    assert products[1]["market_reference"]["sample_size"] == 2


def test_ingest_market_data_rejects_bad_rows_before_writing(tmp_path):
    input_path = tmp_path / "bad_sold_comps.csv"
    products_path = tmp_path / "products.json"
    comps_path = tmp_path / "market_comps.json"
    manifest_path = tmp_path / "dataset_manifest.json"
    _write_csv(
        input_path,
        [
            {
                "product_name": "Apple iPhone 14 Pro 128GB Unlocked",
                "listing_title": "bad price",
                "sold_price": "not-a-price",
            }
        ],
    )

    try:
        ingest_market_data(
            input_path=input_path,
            products_output=products_path,
            comps_output=comps_path,
            manifest_output=manifest_path,
        )
    except ValueError as exc:
        assert "sold/final price is not parseable" in str(exc)
    else:
        raise AssertionError("expected bad row to fail")

    assert not products_path.exists()
    assert not comps_path.exists()
    assert not manifest_path.exists()


def test_ingest_market_cli_writes_outputs(tmp_path, capsys):
    input_path = tmp_path / "sold_comps.csv"
    products_path = tmp_path / "products.json"
    comps_path = tmp_path / "market_comps.json"
    manifest_path = tmp_path / "dataset_manifest.json"
    _write_csv(
        input_path,
        [
            {
                "product_name": "Apple iPhone 14 Pro 128GB Unlocked",
                "listing_title": "iPhone 14 Pro clean IMEI",
                "sold_price": "575",
                "condition": "used_good",
            }
        ],
    )

    exit_code = main(
        [
            "ingest-market",
            "--input",
            str(input_path),
            "--products-output",
            str(products_path),
            "--comps-output",
            str(comps_path),
            "--manifest-output",
            str(manifest_path),
            "--source",
            "offline_cli_export",
            "--window-days",
            "30",
        ]
    )
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    products = json.loads(products_path.read_text())
    manifest = json.loads(manifest_path.read_text())

    assert exit_code == 0
    assert payload["manifest_output"] == str(manifest_path)
    assert products[0]["market_reference"]["source"] == "offline_cli_export"
    assert products[0]["market_reference"]["window_days"] == 30
    assert comps_path.exists()
    assert manifest["source"] == "offline_cli_export"
    assert manifest["quality"]["missing_sold_at_count"] == 1
    assert manifest["quality"]["price_summary"]["median"] == 575.0


def test_ingest_market_cli_attaches_validated_source_policy(tmp_path, capsys):
    input_path = tmp_path / "sold_comps.csv"
    products_path = tmp_path / "products.json"
    comps_path = tmp_path / "market_comps.json"
    manifest_path = tmp_path / "dataset_manifest.json"
    policy_path = tmp_path / "source_policy.json"
    _write_csv(
        input_path,
        [
            {
                "product_name": "Apple iPhone 14 Pro 128GB Unlocked",
                "listing_title": "iPhone 14 Pro clean IMEI",
                "sold_price": "575",
                "condition": "used_good",
            }
        ],
    )
    write_market_source_policy(
        policy_path,
        source_id="ebay_offline_export",
        adapter_kind="offline_export",
        collection_mode="offline_export",
        data_rights="user_provided_export",
    )

    exit_code = main(
        [
            "ingest-market",
            "--input",
            str(input_path),
            "--products-output",
            str(products_path),
            "--comps-output",
            str(comps_path),
            "--manifest-output",
            str(manifest_path),
            "--source",
            "ebay_offline_export",
            "--source-policy",
            str(policy_path),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    manifest = json.loads(manifest_path.read_text())

    assert exit_code == 0
    assert payload["source_policy"] == str(policy_path)
    assert manifest["source_policy"]["source_id"] == "ebay_offline_export"
    assert manifest["source_policy"]["collection_mode"] == "offline_export"
    assert manifest["source_policy"]["live_collection_enabled"] is False
    assert manifest["source_policy"]["validation_status"] == "passed"


def _write_csv(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
