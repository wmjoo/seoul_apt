import unittest
import pandas as pd
from trade_compare import (
    common_areas,
    filter_comparison,
    preferred_overlay_area,
    overlay_colors,
    overlay_style,
    build_overlay,
    build_overlay_volume,
    display_label,
    complex_options,
    area_choices,
    parse_area_choice,
    format_compare_table,
    monthly_trade_counts,
    COMPARE_TABLE_COLS,
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
        table = format_compare_table(filter_comparison(frame, "2022-01", "2022-12", 84, False).assign(
            전용면적=lambda d: d["전용면적_num"], 층=lambda d: d["층_num"], 거래금액_만원=100000,
        ))
        self.assertTrue((pd.to_numeric(table["전용면적"]) >= 84).all())
        self.assertTrue((pd.to_numeric(table["전용면적"]) < 85).all())

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

    def test_label_and_area_helpers_never_return_none(self):
        labels = {"a": "종암에스케이(성북구 종암동) [1,318세대]"}
        frame = pd.DataFrame({"_complex": ["b", "a", None]})
        options = complex_options(frame, labels)
        self.assertEqual(options, ["b", "a"])
        self.assertTrue(all(isinstance(display_label(labels, key), str) for key in options))
        self.assertEqual(area_choices([59, 84]), ["전체", "59", "84"])
        self.assertEqual(parse_area_choice("전체"), "전체")
        self.assertEqual(parse_area_choice("84"), 84)

    def test_default_compare_picks_jongam_sk_and_cheongnyangni_hansin(self):
        from trade_compare import default_compare_picks
        frame = pd.DataFrame([
            {"구": "성북구", "법정동": "종암동", "아파트명": "종암에스케이", "지번": "130"},
            {"구": "동대문구", "법정동": "청량리동", "아파트명": "청량리한신1차", "지번": "59"},
            {"구": "동대문구", "법정동": "청량리동", "아파트명": "청량리한신", "지번": "60"},
            {"구": "동대문구", "법정동": "장안동", "아파트명": "장안한신", "지번": "555"},
        ])
        picks = default_compare_picks(frame)
        self.assertEqual([item["gu"] for item in picks], ["성북구", "동대문구"])
        self.assertIn("종암에스케이", picks[0]["key"])
        self.assertIn("청량리한신", picks[1]["key"])
        self.assertNotIn("1차", picks[1]["key"])
        self.assertIn("종암동", picks[0]["label"])
        self.assertIn("청량리동", picks[1]["label"])

    def test_seed_compare_picks_does_not_need_trades(self):
        from trade_compare import seed_compare_picks, apartment_options_for_gu, _frames_for_picked
        apartments = pd.DataFrame([
            {"아파트명": "종암에스케이", "자치구": "성북구", "동": "종암동", "세대수": 1318},
            {"아파트명": "청량리한신", "자치구": "동대문구", "동": "청량리동", "세대수": 960},
            {"아파트명": "청량리한신1차", "자치구": "동대문구", "동": "청량리동", "세대수": 610},
        ])
        picks = seed_compare_picks(apartments, ["성북구", "동대문구"])
        self.assertEqual([item["gu"] for item in picks], ["성북구", "동대문구"])
        self.assertTrue(all("key" not in item or not item.get("key") for item in picks))
        self.assertIn("1,318세대", picks[0]["label"])
        options, labels = apartment_options_for_gu(apartments, "동대문구")
        self.assertTrue(any("청량리한신" in labels[k] and "1차" not in labels[k] for k in options))
        trades = pd.DataFrame([
            {"구": "성북구", "법정동": "종암동", "아파트명": "종암에스케이", "지번": "130"},
            {"구": "동대문구", "법정동": "청량리동", "아파트명": "청량리한신", "지번": "60"},
        ])
        _, frames, resolved = _frames_for_picked(
            picks, lambda force=False, districts=None: trades, lambda frame: frame, False,
        )
        self.assertEqual(len(frames), 2)
        self.assertTrue(all(not df.empty for df in frames))
        self.assertIn("종암에스케이", resolved[0]["key"])

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

    def test_compare_table_keeps_only_requested_columns(self):
        frame = pd.DataFrame({
            "계약일": pd.to_datetime(["2024-01-02", "2024-03-15"]),
            "구": ["성북구", "성북구"],
            "아파트명": ["종암에스케이", "종암에스케이"],
            "전용면적": [84.72, 59.9],
            "평": [25.6, 18.1],
            "층": [8, 3],
            "거래금액_만원": [125000, 98000],
            "거래유형": ["중개거래", "중개거래"],
        })
        table = format_compare_table(frame)
        self.assertEqual(list(table.columns), COMPARE_TABLE_COLS)
        self.assertEqual(table["계약일"].tolist(), ["2024-03-15", "2024-01-02"])
        self.assertEqual(table["거래가격"].tolist(), ["9억 8,000", "12억 5,000"])
        self.assertEqual(table["층"].tolist(), ["3", "8"])

    def test_overlay_volume_matches_price_colors_and_symbols(self):
        frames = [
            pd.DataFrame({"계약일": pd.to_datetime(["2024-01-05", "2024-01-20", "2024-03-01"])}),
            pd.DataFrame({"계약일": pd.to_datetime(["2024-02-01"])}),
        ]
        labels = ["A단지", "B단지"]
        counts = monthly_trade_counts(frames[0], "2024-01", "2024-03")
        self.assertEqual(counts.tolist(), [2, 0, 1])
        fig = build_overlay_volume(frames, labels, "2024-01", "2024-03", 84)
        self.assertEqual(len(fig.data), 2)
        self.assertIn("건수", fig.layout.title.text)
        for index, trace in enumerate(fig.data):
            color, symbol = overlay_style(index, 2)
            self.assertEqual(trace.marker.color, color)
            self.assertEqual(trace.line.color, color)
            self.assertEqual(trace.marker.symbol, symbol)
            self.assertEqual(trace.mode, "lines+markers")
