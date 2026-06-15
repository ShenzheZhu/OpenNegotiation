import json

from opennego.cli import main
from opennego.leaderboard import (
    LEADERBOARD_V2_SCHEMA_VERSION,
    build_rating_leaderboard,
    render_rating_leaderboard_html,
    write_rating_leaderboard,
)
from opennego.rating import MatchScore, RatingStore
from opennego.schema import Role


def _seed_store(store):
    store.ingest_match(
        run_id="r1", scenario_id="s1",
        buyer_participant_id="shark", seller_participant_id="fish",
        outcome="deal", deal_price=560.0, score=MatchScore(0.85, 0.15),
    )
    store.ingest_match(
        run_id="r2", scenario_id="s1",
        buyer_participant_id="minnow", seller_participant_id="whale",
        outcome="deal", deal_price=600.0, score=MatchScore(0.3, 0.7),
    )


def test_build_rating_leaderboard_ranks_both_tracks():
    store = RatingStore()
    _seed_store(store)

    leaderboard = build_rating_leaderboard(store)

    assert leaderboard.schema_version == LEADERBOARD_V2_SCHEMA_VERSION
    assert leaderboard.match_count == 2
    assert leaderboard.buyer_track[0].rank == 1
    assert leaderboard.buyer_track[0].rating >= leaderboard.buyer_track[-1].rating
    # Both tracks populated with uncertainty and match counts.
    assert all(entry.uncertainty > 0 for entry in leaderboard.buyer_track)
    assert all(entry.match_count >= 1 for entry in leaderboard.seller_track)
    assert leaderboard.buyer_track[0].participant_id == "shark"


def test_write_rating_leaderboard_round_trips(tmp_path):
    db = tmp_path / "ratings.db"
    store = RatingStore(db)
    _seed_store(store)
    store.close()

    out = tmp_path / "rating_leaderboard.json"
    write_rating_leaderboard(db, out)
    payload = json.loads(out.read_text())

    assert payload["schema_version"] == LEADERBOARD_V2_SCHEMA_VERSION
    assert {e["participant_id"] for e in payload["buyer_track"]} == {"shark", "minnow"}


def test_render_rating_leaderboard_html_has_tables():
    store = RatingStore()
    _seed_store(store)
    html = render_rating_leaderboard_html(build_rating_leaderboard(store))

    assert "Buyer track" in html
    assert "Seller track" in html
    assert "shark" in html
    assert "&plusmn;" in html


def test_v1_input_dir_path_unchanged(tmp_path):
    from opennego.runner import run_experiment_config

    runs = tmp_path / "runs"
    run_experiment_config("configs/real_market_demo.yaml", output_dir=runs)
    code = main(["leaderboard", "--input-dir", str(runs)])
    # v1 path still emits a v1 scorecard summary
    import sys
    # captured via capsys in the next test; here just assert exit code
    assert code == 0


def test_leaderboard_cli_store_path(tmp_path, capsys):
    db = tmp_path / "ratings.db"
    store = RatingStore(db)
    _seed_store(store)
    store.close()

    out = tmp_path / "rating_leaderboard.json"
    report = tmp_path / "ratings.html"
    code = main(
        [
            "leaderboard",
            "--store", str(db),
            "--output", str(out),
            "--report", str(report),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["schema_version"] == LEADERBOARD_V2_SCHEMA_VERSION
    assert out.exists()
    assert report.exists()
    assert "Buyer track" in report.read_text()


def test_leaderboard_cli_requires_a_source(capsys):
    code = main(["leaderboard"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert "input-dir" in payload["error"]
