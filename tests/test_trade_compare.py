import unittest
import pandas as pd
from trade_compare import common_areas, filter_comparison


class CompareTests(unittest.TestCase):
    def test_common_area_intersection_sorted(self):
        frames = [pd.DataFrame({"전용면적_num": values}) for values in
                  ([84.72, 59.9, 101, None], [59.9, 84.72, 120], [84.72, 59.9, 84.73])]
        self.assertEqual(common_areas(frames), [59.9, 84.72])
        self.assertEqual(common_areas(frames + [pd.DataFrame({"전용면적_num": [84.73]})]), [])

    def test_period_area_and_floor_filters_sync(self):
        frame = pd.DataFrame({"계약년월": ["2021-01", "2022-06", "2022-07", "2022-07"],
                              "전용면적_num": [84.72, 84.72, 59.9, 84.72], "층_num": [3, 1, 5, 8]})
        self.assertEqual(len(filter_comparison(frame, "2022-01", "2022-12")), 3)
        result = filter_comparison(frame, "2022-01", "2022-12", 84.72, True)
        self.assertEqual(result.index.tolist(), [3])
