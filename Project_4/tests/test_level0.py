"""Level 0 (R1-R3) against check_values.csv and basic invariants."""

from fleetopt.level0 import check_against_reference, level0_table, max_removable


def test_matches_check_values(inst):
    bad = check_against_reference(inst)
    assert bad.empty, bad.to_string()


def test_full_grid(inst):
    t = level0_table(inst)
    assert len(t) == len(inst.stations) * len(inst.categories) * 14
    assert not t.duplicated(["station_id", "category", "day"]).any()
    assert t.notna().all().all()


def test_do_nothing_is_valid(inst):
    assert (level0_table(inst)["slack"] >= 0).all()


def test_oneway_flows_balance(inst):
    t = level0_table(inst)
    per_cat = t.groupby("category")[["oneway_arrivals", "oneway_departures"]].sum()
    assert (per_cat["oneway_arrivals"] == per_cat["oneway_departures"]).all()


def test_total_fleet_constant_per_category(inst):
    t = level0_table(inst)
    total = t.groupby(["category", "day"])["station_fleet"].sum().unstack()
    assert (total.nunique(axis=1) == 1).all()
    assert total[1].sum() == len(inst.fleet_snapshot)


def test_max_removable_is_suffix_min(inst):
    t = level0_table(inst)
    t["max_removable"] = max_removable(t)
    for _, g in t.groupby(["station_id", "category"]):
        slack = g.sort_values("day")["slack"].to_numpy()
        expected = [slack[i:].min() for i in range(len(slack))]
        assert g.sort_values("day")["max_removable"].tolist() == expected
