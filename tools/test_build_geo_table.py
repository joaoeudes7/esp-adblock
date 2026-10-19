#!/usr/bin/env python3
"""Runnable check for tools/build_geo_table.py (no input file needed)."""
import unittest

import build_geo_table as geo


class TestGeoTable(unittest.TestCase):
    def setUp(self):
        self.table, self.codes = geo.build_table(geo.fixture_rows())
        self.base = 0x0A000000 >> geo.SHIFT

    def test_codes_are_sorted_and_reserved_excluded(self):
        self.assertEqual(self.codes, ["CN", "DE", "FR", "JP", "US"])
        self.assertNotIn("ZZ", self.codes)

    def test_size_is_one_byte_per_14(self):
        self.assertEqual(len(self.table), 16384)
        self.assertEqual(len(self.table), geo.N)

    def test_unanimous_block_keeps_its_country(self):
        self.assertEqual(self.table[self.base], self.codes.index("DE"))

    def test_majority_above_threshold_keeps_the_block(self):
        # 70/30 FR/US -> FR survives the 60% rule
        self.assertEqual(self.table[self.base + 1], self.codes.index("FR"))

    def test_majority_below_threshold_is_neutral(self):
        # 55/45 JP/CN -> too mixed, must not paint a wrong country
        self.assertEqual(self.table[self.base + 2], geo.UNKNOWN)

    def test_reserved_block_is_neutral(self):
        self.assertEqual(self.table[self.base + 3], geo.UNKNOWN)

    def test_lower_threshold_keeps_a_55pc_majority(self):
        table, codes = geo.build_table(geo.fixture_rows(), min_share=0.50)
        self.assertEqual(table[(0x0A000000 >> geo.SHIFT) + 2], codes.index("JP"))

    def test_header_layout(self):
        header = geo.render_header(self.table, self.codes, "fixture.csv")
        self.assertIn("#define GEO_TABLE_N 16384", header)
        self.assertIn("#define GEO_NCODES 5", header)
        self.assertIn("CC BY 4.0", header)
        self.assertIn('"CNDEFRJPUS"', header)


if __name__ == "__main__":
    unittest.main()
