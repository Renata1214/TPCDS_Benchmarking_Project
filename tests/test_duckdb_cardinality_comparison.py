import unittest

from scripts.compare_duckdb_cardinalities import (
    compare_operator_trees,
    flatten_plan,
    parse_cardinality,
    parse_explain_json,
)


class CardinalityComparisonTests(unittest.TestCase):
    def test_estimated_and_actual_counts_match_by_tree_path(self):
        explain = [
            {
                "name": "PROJECTION",
                "children": [
                    {
                        "name": "SEQ_SCAN ",
                        "children": [],
                        "extra_info": {"Estimated Cardinality": "1,200"},
                    },
                    {
                        "name": "SEQ_SCAN ",
                        "children": [],
                        "extra_info": {"Estimated Cardinality": "400"},
                    },
                ],
                "extra_info": {"Estimated Cardinality": "1,600"},
            }
        ]
        profile = {
            "children": [
                {
                    "operator_type": "PROJECTION",
                    "operator_cardinality": 1500,
                    "extra_info": {"Estimated Cardinality": "1600"},
                    "children": [
                        {
                            "operator_type": "TABLE_SCAN",
                            "operator_cardinality": 1100,
                            "extra_info": {"Estimated Cardinality": "1200"},
                            "children": [],
                        },
                        {
                            "operator_type": "TABLE_SCAN",
                            "operator_cardinality": 0,
                            "extra_info": {"Estimated Cardinality": "400"},
                            "children": [],
                        },
                    ],
                }
            ]
        }

        rows = compare_operator_trees(
            1,
            "query1",
            flatten_plan(explain, "explain"),
            flatten_plan(profile["children"], "profile"),
            "query1.explain.json",
            "query1.profile.json",
        )

        self.assertEqual([row["operator_path"] for row in rows], ["0", "0/0", "0/1"])
        self.assertEqual([row["comparison_status"] for row in rows], ["matched"] * 3)
        self.assertEqual(rows[1]["estimated_rows"], 1200)
        self.assertEqual(rows[1]["actual_rows"], 1100)
        self.assertEqual(rows[1]["absolute_difference"], 100)
        self.assertAlmostEqual(rows[1]["estimated_to_actual_ratio"], 1200 / 1100)
        self.assertEqual(rows[2]["actual_rows"], 0)
        self.assertEqual(rows[2]["estimated_to_actual_ratio"], "")
        self.assertEqual(rows[1]["match_confidence"], "medium")

    def test_type_mismatch_is_not_reported_as_a_numeric_comparison(self):
        rows = compare_operator_trees(
            1,
            "query2",
            {"0": {"operator_type": "HASH_JOIN", "estimated_rows": 12, "actual_rows": None}},
            {"0": {"operator_type": "FILTER", "estimated_rows": 12, "actual_rows": 10}},
            "query2.explain.json",
            "query2.profile.json",
        )

        self.assertEqual(rows[0]["comparison_status"], "operator_type_mismatch")
        self.assertEqual(rows[0]["absolute_difference"], "")
        self.assertEqual(rows[0]["estimate_consistency"], "not_comparable")

    def test_unmatched_paths_and_missing_metrics_are_explicit(self):
        rows = compare_operator_trees(
            1,
            "query3",
            {"0": {"operator_type": "FILTER", "estimated_rows": None, "actual_rows": None}},
            {
                "0": {"operator_type": "FILTER", "estimated_rows": None, "actual_rows": 0},
                "0/0": {"operator_type": "TABLE_SCAN", "estimated_rows": None, "actual_rows": 5},
            },
            "query3.explain.json",
            "query3.profile.json",
        )

        self.assertEqual(rows[0]["comparison_status"], "missing_estimate")
        self.assertEqual(rows[0]["absolute_difference"], "")
        self.assertEqual(rows[1]["comparison_status"], "unmatched_in_explain")
        self.assertEqual(rows[1]["match_confidence"], "low")

    def test_descendants_of_mismatched_operators_are_not_compared(self):
        rows = compare_operator_trees(
            1,
            "query4",
            {
                "0": {"operator_type": "FILTER", "estimated_rows": 20, "actual_rows": None},
                "0/0": {"operator_type": "HASH_JOIN", "estimated_rows": 10, "actual_rows": None},
                "0/0/0": {"operator_type": "TABLE_SCAN", "estimated_rows": 5, "actual_rows": None},
            },
            {
                "0": {"operator_type": "FILTER", "estimated_rows": 20, "actual_rows": 15},
                "0/0": {"operator_type": "UNION", "estimated_rows": 10, "actual_rows": 12},
                "0/0/0": {"operator_type": "TABLE_SCAN", "estimated_rows": 5, "actual_rows": 8},
            },
            "query4.explain.json",
            "query4.profile.json",
        )

        self.assertEqual(rows[0]["comparison_status"], "matched")
        self.assertEqual(rows[1]["comparison_status"], "operator_type_mismatch")
        self.assertEqual(rows[2]["comparison_status"], "untrusted_subtree")
        self.assertEqual(rows[2]["absolute_difference"], "")
        self.assertEqual(rows[2]["estimate_consistency"], "not_comparable")

    def test_json_plan_parser_accepts_duckdb_cli_banner_and_trailing_marker(self):
        output = (
            "Physical Plan\n"
            "[{\"name\":\"FILTER\",\"children\":[],"
            "\"extra_info\":{\"Estimated Cardinality\":\"7\"}}]"
            "__END_MARKER__"
        )

        plan = parse_explain_json(output)

        self.assertEqual(plan[0]["name"], "FILTER")
        self.assertEqual(parse_cardinality(plan[0]["extra_info"]["Estimated Cardinality"]), 7)


if __name__ == "__main__":
    unittest.main()
