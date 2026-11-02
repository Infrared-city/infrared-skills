from __future__ import annotations

import pytest

from ir_dynamo import targets as t


@pytest.mark.parametrize(
    "text,expected",
    [
        ("ground", ["ground"]),
        (" Facades ", ["facades"]),
        ("both", ["ground", "facades"]),
        ("ALL", ["ground", "facades"]),
    ],
)
def test_parse_target(text: str, expected: list) -> None:
    assert t.parse_target(text) == expected


def test_bad_target_lists_the_valid_values() -> None:
    with pytest.raises(ValueError, match="ground, facades, both, all"):
        t.parse_target("roofs")


def test_both_runs_a_shared_analysis_twice() -> None:
    assert t.plan_runs("both", "svf") == (["ground", "facades"], [])
    assert t.plan_runs("both", "Sun Hours")[0] == ["ground", "facades"]


def test_both_skips_the_target_without_the_analysis() -> None:
    run, skipped = t.plan_runs("both", "wind")
    assert run == ["ground"]
    assert len(skipped) == 1 and "Skipped facades" in skipped[0]
    run, skipped = t.plan_runs("all", "daylight")
    assert run == ["facades"] and "Skipped ground" in skipped[0]


def test_one_target_still_refuses_a_wrong_analysis() -> None:
    assert t.plan_runs("ground", "wind") == (["ground"], [])
    with pytest.raises(ValueError, match="does not run on facades"):
        t.plan_runs("facades", "wind")


def test_both_refuses_an_unknown_label() -> None:
    with pytest.raises(ValueError, match="unknown.*svf"):
        t.plan_runs("both", "nope")


def test_combined_cost_sums_tokens() -> None:
    outs = {
        "ground": {"cost": "2 tile(s), about 30 tokens", "tokens": 30},
        "facades": {"cost": "1 tile(s), about 12 tokens", "tokens": 12},
    }
    text = t.combined_cost(outs)
    assert "ground: 2 tile(s)" in text and "facades: 1 tile(s)" in text
    assert text.endswith("Total: about 42 tokens")
    assert t.combined_cost({"ground": outs["ground"]}) == "ground: 2 tile(s), about 30 tokens"


OLD_GROUND = {
    "result": {"kind": "points", "values": [1]},
    "title": "Sky view factor",
    "unit": "%",
    "true_north_rad": 0.1,
}


def test_old_single_result_file_is_read() -> None:
    (entry,) = t.load_entries(OLD_GROUND)
    assert entry["target"] == "ground" and entry["title"] == "Sky view factor"
    old_facade = dict(OLD_GROUND, result={"kind": "triangles", "values": [1]})
    assert t.load_entries(old_facade)[0]["target"] == "facades"
    assert t.load_entries({}) == [] and t.load_entries(None) == []


def test_merge_replaces_same_target_and_keeps_the_other() -> None:
    new_facade = {"target": "facades", "result": {"kind": "triangles"}, "title": "F", "unit": "%"}
    merged = t.merge_entries(OLD_GROUND, [new_facade])
    assert [e["target"] for e in merged["entries"]] == ["ground", "facades"]
    new_ground = dict(new_facade, target="ground", title="G2")
    again = t.merge_entries(merged, [new_ground])
    titles = {e["target"]: e["title"] for e in again["entries"]}
    assert titles == {"ground": "G2", "facades": "F"}
    assert t.load_entries(again) == again["entries"]
