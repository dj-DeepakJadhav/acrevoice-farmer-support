import unittest

from acrevoice.io import correction_csv, record_from_csv


class IOTests(unittest.TestCase):
    def test_reads_import_csv_into_one_case_per_row(self):
        cases = record_from_csv(
            "holding_id,holding_name,application_year,scheme_code,area_ha\n"
            "DE-1,Hof Eins,2026,OER2,\n"
            "DE-2,Hof Zwei,2026,GLOEZ6,3.4\n"
        )
        self.assertEqual(len(cases), 2)
        first = cases[0]
        self.assertEqual(first["scheme_code"], "OER2")
        self.assertEqual(first["holding_name"], "Hof Eins")
        self.assertEqual(first["application_year"], "2026")
        self.assertEqual(first["record"], {
            "holding_id": "DE-1", "holding_name": "Hof Eins",
            "application_year": "2026", "scheme_code": "OER2", "area_ha": "",
        })

    def test_exports_changes(self):
        csv_text = correction_csv({"changes": [{"field": "area_ha", "original": "", "proposed": "42.5", "confirmed": True, "captured_at": "now"}]})
        self.assertIn("area_ha", csv_text)
        self.assertIn("42.5", csv_text)
