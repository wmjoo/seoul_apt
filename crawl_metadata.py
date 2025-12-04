"""
서울시 공동주택 아파트 정보 (메타데이터) 수집 스크립트
데이터셋: OA-15818
1000개씩 배치로 전체 데이터 수집
"""
from crawler import SeoulApartmentCrawler
import os
import sys

def main():
    crawler = SeoulApartmentCrawler()
    
    print("=" * 60)
    print("서울시 공동주택 아파트 정보 (메타데이터) 수집")
    print("=" * 60)
    print("데이터셋: OA-15818")
    print("URL: https://data.seoul.go.kr/dataList/OA-15818/S/1/datasetView.do")
    print("방식: 1000개씩 배치로 전체 데이터 수집")
    print("=" * 60)
    
    # 방법 1: API로 수집 시도 (1000개씩)
    print("\n[방법 1] Open API를 통한 자동 수집 (1000개씩 배치)")
    print("-" * 60)
    
    # 먼저 작은 범위로 테스트
    print("테스트: 1~100건 수집 시도...")
    test_df = crawler.crawl_seoul_apartment_info(1, 100)
    
    if not test_df.empty:
        print(f"✅ API 테스트 성공! {len(test_df)}건 수집")
        print("\n전체 데이터 수집 시작 (1000개씩 배치)...")
        
        # 전체 데이터 수집 (1000개씩 자동 분할)
        all_df = crawler.crawl_seoul_apartment_info_all(max_records=50000)
        
        if not all_df.empty:
            processed_df = crawler.process_seoul_apartment_info_data(all_df)
            crawler.save_to_csv(processed_df, "seoul_apartments_metadata.csv")
            
            print("\n" + "=" * 60)
            print("✅ API를 통한 수집 완료!")
            print("=" * 60)
            print(f"총 {len(processed_df)}건의 아파트 메타데이터")
            print(f"저장 파일: seoul_apartments_metadata.csv")
            return
        else:
            print("⚠️  전체 데이터 수집 실패")
    else:
        print("⚠️  API 테스트 실패 - CSV 파일 방식으로 전환")
    
    # 방법 2: CSV 파일이 있는 경우
    print("\n[방법 2] CSV 파일 자동 검색 및 로드")
    print("-" * 60)
    
    csv_file = None
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
        print(f"지정된 CSV 파일: {csv_file}")
    else:
        # 자동 검색
        import glob
        possible_files = glob.glob("*OA-15818*.csv") + glob.glob("*아파트*정보*.csv") + glob.glob("*공동주택*.csv")
        if possible_files:
            csv_file = possible_files[0]
            print(f"✅ CSV 파일 발견: {csv_file}")
        else:
            print("⚠️  CSV 파일을 찾을 수 없습니다.")
            print("\n📥 CSV 파일 다운로드 방법:")
            print("   1. https://data.seoul.go.kr/dataList/OA-15818/S/1/datasetView.do 접속")
            print("   2. '파일내려받기' 또는 'CSV 다운로드' 클릭")
            print("   3. 다운로드한 파일을 프로젝트 폴더에 저장")
            print("   4. 이 스크립트를 다시 실행하거나 파일 경로를 인자로 전달")
            print("      예: python crawl_metadata.py 다운로드한파일.csv")
            print("\n💡 참고: CSV 파일을 다운로드하면 전체 데이터를 한 번에 수집할 수 있습니다.")
            return
    
    if csv_file and os.path.exists(csv_file):
        print(f"\n📂 CSV 파일 처리 중: {csv_file}")
        result_df = crawler.crawl_seoul_apartment_info_all_with_csv(csv_file)
        
        if not result_df.empty:
            print("\n" + "=" * 60)
            print("✅ 수집 완료!")
            print("=" * 60)
            print(f"총 {len(result_df)}건의 아파트 메타데이터")
            print(f"저장 파일: seoul_apartments_metadata.csv")
            print("\n데이터 통계:")
            if result_df['자치구'].notna().any():
                print(f"  - 자치구: {result_df['자치구'].nunique()}개")
            if result_df['건축연도'].notna().any():
                print(f"  - 건축연도 범위: {result_df['건축연도'].min()} ~ {result_df['건축연도'].max()}")
            if result_df['세대수'].notna().any():
                print(f"  - 세대수 합계: {result_df['세대수'].sum():,.0f}세대")
            print("\n샘플 데이터 (상위 5개):")
            print(result_df.head())
        else:
            print("❌ 데이터 처리 실패")
    else:
        print(f"❌ 파일을 찾을 수 없습니다: {csv_file}")

if __name__ == "__main__":
    main()

