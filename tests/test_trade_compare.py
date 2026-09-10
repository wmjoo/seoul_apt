import unittest
import pandas as pd
from trade_compare import (
    common_areas,
    filter_comparison,
    preferred_overlay_area,
    overlay_colors,
    build_overlay,
)


class CompareTests(unittest.TestCase):
    def test_common_area_intersection_sorted(self):
        frames = [pd.DataFrame({"전용면적_num": values}) for values in
                  ([84.72, 59.9, 101, None], [59.9, 84.72, 120], [84.72, 59.9, 84.73])]
        self.assertEqual(common_areas(frames), [59, 84])
        self.assertEqual(common_areas(frames + [pd.DataFrame({"전용면적_num": [114.73]})]), [])

    def test_period_area_and_floor_filters_sync(self):
        frame = pd.DataFrame({"계약년월": ["2021-01", "2022-06", "2022-07", "2022-07"],
                              "전용면적_num": [84.72, 84.72, 59.9, 84.72], "층_num": [3, 1, 5, 8]})
        frame["계약일"] = pd.to_datetime(frame["계약년월"] + "-01")
        self.assertEqual(len(filter_comparison(frame, "2022-01", "2022-12")), 3)
        result = filter_comparison(frame, "2022-01", "2022-12", 84, True)
        self.assertEqual(result.index.tolist(), [3])

    def test_half_year_boundary_and_zero_counts(self):
        from trade_compare import half_year_activity
        frames = [pd.DataFrame({"계약일": pd.to_datetime(["2025-06-30", "2025-07-01"])}),
                  pd.DataFrame({"계약일": pd.to_datetime(["2025-08-01"])})]
        result = half_year_activity(frames, ["A", "B"], "2025-01", "2026-09")
        self.assertEqual(result["반기"].tolist(), ["2025 상반기", "2025 하반기", "2026 상반기", "2026 하반기"])
        self.assertEqual(result["A"].tolist(), [1, 1, 0, 0])
        self.assertEqual(result["B"].tolist(), [0, 1, 0, 0])

    def test_complex_label_metadata_and_missing(self):
        from trade_compare import complex_labels
        frame = pd.DataFrame([{"_complex": "a", "아파트명": "종암에스케이", "구": "성북구", "법정동": "종암동"},
                              {"_complex": "b", "아파트명": "B", "구": "강남구", "법정동": "역삼동"}])
        metadata = pd.DataFrame([{"아파트명": "종암SK", "자치구": "성북구", "동": "종암동", "세대수": 1318}])
        labels = complex_labels(frame, metadata)
        self.assertEqual(labels["a"], "종암에스케이(성북구 종암동) [1,318세대]")
        self.assertIn("세대수 미상", labels["b"])

    def test_preferred_overlay_area_picks_most_common_shared(self):
        frames = [pd.DataFrame({"전용면적_num": [84.72, 84.1, 59.9]}),
                  pd.DataFrame({"전용면적_num": [84.99, 59.2, 84.3, 114.1]})]
        self.assertEqual(preferred_overlay_area(frames, [59, 84]), 84)

    def test_overlay_colors_contrast_by_count(self):
        two, three = overlay_colors(2), overlay_colors(3)
        self.assertEqual(len(set(two)), 2)
        self.assertEqual(len(set(three)), 3)
        self.assertEqual(two[0], three[0])
        self.assertNotEqual(two[0], two[1])

    def test_overlay_chart_has_trace_per_complex(self):
        frames = [
            pd.DataFrame({"계약일": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"]),
                          "거래금액_만원": [80000, 81000, 82000, 83000],
                          "전용면적_num": [84.12, 84.12, 84.12, 84.12], "층_num": [3, 5, 7, 8]}),
            pd.DataFrame({"계약일": pd.to_datetime(["2024-01-15", "2024-03-01", "2024-05-01", "2024-06-01"]),
                          "거래금액_만원": [90000, 91000, 92000, 93000],
                          "전용면적_num": [84.88, 84.88, 84.88, 84.88], "층_num": [2, 4, 6, 10]}),
        ]
        labels = ["A단지(성북구 종암동) [1,000세대]", "B단지(강남구 역삼동) [800세대]"]
        fig = build_overlay(frames, labels, "2024-01", "2024-06", 84)
        names = [trace.name for trace in fig.data]
        self.assertGreaterEqual(names.count(labels[0]), 1)
        self.assertGreaterEqual(names.count(labels[1]), 1)
        self.assertIn("84㎡", fig.layout.title.text)
