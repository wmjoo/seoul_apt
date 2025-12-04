"""
서울 아파트 데이터 크롤러
공공데이터포털 API와 네이버 부동산 크롤링을 결합
"""
import requests
import pandas as pd
import time
import json
import urllib.parse
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from config import (
    PUBLIC_DATA_API_KEY, 
    SEOUL_DATA_API_KEY,
    SEOUL_REAL_ESTATE_DATASET_ID,
    SEOUL_APARTMENT_INFO_DATASET_ID,
    SEOUL_DISTRICTS, 
    CRAWL_DELAY
)
from utils import extract_district, calculate_pyeong, calculate_distance_to_subway


class SeoulApartmentCrawler:
    """서울 아파트 데이터 크롤러"""
    
    def __init__(self):
        # API 키가 이미 URL 인코딩되어 있으면 디코딩
        self.api_key = PUBLIC_DATA_API_KEY
        if self.api_key and self.api_key != "YOUR_API_KEY_HERE":
            try:
                # 이미 인코딩된 키를 디코딩 (requests가 자동 인코딩하므로)
                decoded = urllib.parse.unquote(self.api_key)
                self.api_key = decoded
            except:
                pass
        
        # 서울 열린데이터광장 API 키
        self.seoul_api_key = SEOUL_DATA_API_KEY
        self.seoul_dataset_id = SEOUL_REAL_ESTATE_DATASET_ID
        self.seoul_apartment_info_dataset_id = SEOUL_APARTMENT_INFO_DATASET_ID
        
        # 공공데이터포털 국토교통부 아파트 실거래가 API (HTTPS 사용)
        self.base_url = "https://openapi.molit.go.kr/OpenAPI_ToolInstallPackage/service/rest/RTMSOBJSvc/getRTMSDataSvcAptRent"
        
        # 서울 열린데이터광장 API 엔드포인트
        self.seoul_api_base = "http://openapi.seoul.go.kr:8088"
        self.data = []
    
    def test_api_key(self) -> bool:
        """
        API 키가 올바르게 설정되어 있는지 테스트
        
        Returns:
            bool: API 키가 유효하면 True
        """
        if not self.api_key or self.api_key == "YOUR_API_KEY_HERE":
            print("❌ API 키가 설정되지 않았습니다.")
            print("   config.py 파일에서 PUBLIC_DATA_API_KEY를 확인하세요.")
            return False
        
        print(f"📝 API 키 확인: {self.api_key[:20]}... (처음 20자)")
        
        # 간단한 테스트 요청 (서울시 강남구, 2024년 1월)
        try:
            # 공공데이터포털 API는 serviceKey를 쿼리 파라미터로 직접 전달
            # URL에 직접 포함시키는 방식도 가능
            test_url = f"{self.base_url}?serviceKey={urllib.parse.quote(self.api_key)}&LAWD_CD=11680&DEAL_YMD=202401"
            
            response = requests.get(test_url, timeout=10)
            
            if response.status_code == 200:
                # XML 응답 확인
                if "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in response.text:
                    print("❌ API 키가 등록되지 않았거나 잘못되었습니다.")
                    print("   공공데이터포털에서 API 키를 확인하세요.")
                    return False
                elif "NODATA_ERROR" in response.text:
                    print("✅ API 키는 유효하지만 해당 기간에 데이터가 없습니다.")
                    print("   (이는 정상입니다 - API 키는 올바르게 설정되었습니다)")
                    return True
                else:
                    print("✅ API 키가 올바르게 설정되어 있습니다.")
                    print(f"   응답 상태: {response.status_code}")
                    return True
            else:
                print(f"⚠️ API 응답 오류: {response.status_code}")
                print(f"   응답 내용: {response.text[:300]}")
                return False
        except requests.exceptions.ConnectionError:
            print("❌ 네트워크 연결 오류: API 서버에 연결할 수 없습니다.")
            print("   인터넷 연결을 확인하거나 방화벽 설정을 확인하세요.")
            return False
        except Exception as e:
            print(f"❌ API 테스트 중 오류 발생: {type(e).__name__}")
            print(f"   오류 내용: {str(e)[:200]}")
            return False
    
    def crawl_public_data(self, district: str, year: int = 2024) -> List[Dict]:
        """
        공공데이터포털에서 아파트 정보 크롤링
        
        Args:
            district: 자치구명
            year: 연도
        
        Returns:
            List[Dict]: 아파트 정보 리스트
        """
        apartments = []
        
        # 공공데이터 API는 실제로는 실거래가 데이터를 제공하므로
        # 여기서는 샘플 데이터 구조를 만들고, 실제로는 네이버 부동산을 크롤링하는 방식 사용
        print(f"{district} 데이터 수집 중...")
        time.sleep(CRAWL_DELAY)
        
        return apartments
    
    def crawl_seoul_real_estate(self, start_index: int = 1, end_index: int = 1000) -> pd.DataFrame:
        """
        서울 열린데이터광장에서 부동산 실거래가 데이터 크롤링
        데이터셋 ID: OA-21275
        
        ⚠️ API 사용 제한:
        - 하루 최대 1,000회 요청 가능
        - 1회에 최대 1,000건 요청 가능
        - 1,000건 이상은 나누어서 호출 필요
        
        Args:
            start_index: 시작 인덱스
            end_index: 종료 인덱스 (최대 1000개씩 조회 가능)
        
        Returns:
            pd.DataFrame: 부동산 실거래가 데이터프레임
        """
        """
        서울 열린데이터광장에서 부동산 실거래가 데이터 크롤링
        데이터셋 ID: OA-21275
        
        Args:
            start_index: 시작 인덱스
            end_index: 종료 인덱스 (최대 1000개씩 조회 가능)
        
        Returns:
            pd.DataFrame: 부동산 실거래가 데이터프레임
        """
        if self.seoul_api_key == "YOUR_SEOUL_API_KEY_HERE":
            print("⚠️ 서울 열린데이터광장 API 키가 설정되지 않았습니다.")
            print("   config.py에서 SEOUL_DATA_API_KEY를 설정하세요.")
            print("   또는 CSV 파일을 직접 다운로드하여 사용할 수 있습니다.")
            return pd.DataFrame()
        
        try:
            # 서울 열린데이터광장 Open API 엔드포인트
            # 형식: http://openapi.seoul.go.kr:8088/{인증키}/json/{서비스명}/{시작인덱스}/{종료인덱스}
            # ⚠️ 주의: 1회에 최대 1,000건만 요청 가능
            if end_index - start_index + 1 > 1000:
                print(f"⚠️ 1회 요청은 최대 1,000건까지 가능합니다. (요청: {end_index - start_index + 1}건)")
                end_index = start_index + 999
            
            url = f"{self.seoul_api_base}/{self.seoul_api_key}/json/tbLnOpendataRentV/{start_index}/{end_index}"
            
            print(f"서울 열린데이터광장 API 호출 중... (인덱스: {start_index}~{end_index})")
            response = requests.get(url, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # API 응답 구조 확인
                if 'tbLnOpendataRentV' in data:
                    result = data['tbLnOpendataRentV']
                    
                    if 'row' in result:
                        df = pd.DataFrame(result['row'])
                        print(f"✅ {len(df)}개의 데이터를 수집했습니다.")
                        return df
                    else:
                        print("⚠️ 데이터가 없습니다.")
                        return pd.DataFrame()
                else:
                    print(f"⚠️ API 응답 구조가 예상과 다릅니다: {list(data.keys())}")
                    return pd.DataFrame()
            else:
                print(f"❌ API 호출 실패: {response.status_code}")
                print(f"   응답: {response.text[:200]}")
                return pd.DataFrame()
                
        except Exception as e:
            print(f"❌ 서울 열린데이터광장 크롤링 오류: {type(e).__name__}")
            print(f"   오류 내용: {str(e)[:200]}")
            return pd.DataFrame()
    
    def crawl_seoul_real_estate_all(self, max_records: int = 10000) -> pd.DataFrame:
        """
        서울 열린데이터광장에서 모든 부동산 실거래가 데이터 크롤링
        (여러 번 호출하여 전체 데이터 수집)
        
        Args:
            max_records: 최대 수집할 레코드 수
        
        Returns:
            pd.DataFrame: 전체 부동산 실거래가 데이터프레임
        """
        all_data = []
        start_index = 1
        batch_size = 1000
        
        print(f"서울 열린데이터광장에서 최대 {max_records}개의 데이터를 수집합니다...")
        
        while start_index <= max_records:
            end_index = min(start_index + batch_size - 1, max_records)
            df_batch = self.crawl_seoul_real_estate(start_index, end_index)
            
            if df_batch.empty:
                print("더 이상 데이터가 없습니다.")
                break
            
            all_data.append(df_batch)
            start_index = end_index + 1
            
            # API 호출 제한을 위한 지연
            time.sleep(CRAWL_DELAY)
            
            if len(df_batch) < batch_size:
                print("마지막 배치를 수집했습니다.")
                break
        
        if all_data:
            result_df = pd.concat(all_data, ignore_index=True)
            print(f"\n✅ 총 {len(result_df)}개의 데이터를 수집했습니다.")
            return result_df
        else:
            print("❌ 수집된 데이터가 없습니다.")
            return pd.DataFrame()
    
    def process_seoul_real_estate_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        서울 열린데이터광장에서 수집한 데이터를 앱에서 사용할 형식으로 변환
        
        Args:
            df: 원본 데이터프레임
        
        Returns:
            pd.DataFrame: 변환된 데이터프레임
        """
        if df.empty:
            return df
        
        processed_data = []
        
        for _, row in df.iterrows():
            # 자치구 추출
            district = extract_district(str(row.get('SGG_CD', '')) + str(row.get('BJDONG_NM', '')))
            if not district:
                # 주소에서 자치구 추출 시도
                address = str(row.get('SGG_NM', '')) + str(row.get('BJDONG_NM', ''))
                district = extract_district(address)
            
            # 건축년도
            build_year = row.get('BUILD_YEAR', None)
            try:
                build_year = int(build_year) if pd.notna(build_year) else None
            except:
                build_year = None
            
            # 면적 정보
            area_sqm = row.get('RENT_AREA', None) or row.get('RENT_GBN', None)
            try:
                area_sqm = float(area_sqm) if pd.notna(area_sqm) else None
            except:
                area_sqm = None
            
            pyeong = calculate_pyeong(area_sqm) if area_sqm else None
            
            # 주소 구성
            address = f"서울특별시 {row.get('SGG_NM', '')} {row.get('BJDONG_NM', '')} {row.get('BLDG_NM', '')}"
            address = address.strip()
            
            # 좌표 정보 (있는 경우)
            lat = row.get('LAT', None)
            lon = row.get('LNG', None) or row.get('LON', None)
            
            # 지하철역 거리 계산
            nearest_station = None
            distance_km = None
            if lat and lon:
                try:
                    nearest_station, distance_km = calculate_distance_to_subway(float(lat), float(lon))
                except:
                    pass
            
            apartment = {
                "자치구": district or row.get('SGG_NM', ''),
                "주소": address,
                "건축연도": build_year,
                "세대수": None,  # 실거래가 데이터에는 세대수 정보가 없을 수 있음
                "복도계단식": None,  # 실거래가 데이터에는 이 정보가 없을 수 있음
                "전용면적_제곱미터": area_sqm,
                "평형": pyeong,
                "위도": lat,
                "경도": lon,
                "가장가까운지하철역": nearest_station,
                "지하철역거리_km": distance_km,
                # 추가 정보
                "물건금액": row.get('RENT_GTN', None),
                "보증금": row.get('RENT_DEPOSIT', None),
                "월세": row.get('RENT_FEE', None),
                "신고년도": row.get('CNTRCT_DE', None),
            }
            
            processed_data.append(apartment)
        
        return pd.DataFrame(processed_data)
    
    def crawl_seoul_apartment_info(self, start_index: int = 1, end_index: int = 1000) -> pd.DataFrame:
        """
        서울 열린데이터광장에서 공동주택 아파트 정보 크롤링
        데이터셋 ID: OA-15818 (서울시 공동주택 아파트 정보)
        
        이 데이터셋에는 다음 정보가 포함됩니다:
        - 아파트명, 주소
        - 준공일자 (건축연도)
        - 세대타입 (복도/계단식 정보)
        - 연면적, 관리비부과면적
        - 건설사, 시행사
        - 난방방식 등
        
        ⚠️ API 사용 제한:
        - 하루 최대 1,000회 요청 가능
        - 1회에 최대 1,000건 요청 가능
        - 1,000건 이상은 나누어서 호출 필요
        
        Args:
            start_index: 시작 인덱스
            end_index: 종료 인덱스 (최대 1000개씩 조회 가능)
        
        Returns:
            pd.DataFrame: 아파트 정보 데이터프레임
        """
        if self.seoul_api_key == "YOUR_SEOUL_API_KEY_HERE":
            print("⚠️ 서울 열린데이터광장 API 키가 설정되지 않았습니다.")
            print("   config.py에서 SEOUL_DATA_API_KEY를 설정하세요.")
            print("   또는 CSV 파일을 직접 다운로드하여 사용할 수 있습니다.")
            return pd.DataFrame()
        
        try:
            # 서울 열린데이터광장 Open API 엔드포인트
            # 형식: http://openapi.seoul.go.kr:8088/{인증키}/json/{서비스명}/{시작인덱스}/{종료인덱스}
            # 서비스명은 데이터셋에 따라 다를 수 있음 (일반적으로 데이터셋 ID 기반)
            # ⚠️ 주의: 1회에 최대 1,000건만 요청 가능
            if end_index - start_index + 1 > 1000:
                print(f"⚠️ 1회 요청은 최대 1,000건까지 가능합니다. (요청: {end_index - start_index + 1}건)")
                end_index = start_index + 999
            
            # 서비스명: OpenAptInfo (서울시 공동주택 아파트 정보)
            # API 엔드포인트: http://openapi.seoul.go.kr:8088/{인증키}/json/OpenAptInfo/{시작}/{종료}
            service_name = "OpenAptInfo"
            url = f"{self.seoul_api_base}/{self.seoul_api_key}/json/{service_name}/{start_index}/{end_index}"
            
            print(f"서울 열린데이터광장 아파트 정보 API 호출 중... (인덱스: {start_index}~{end_index})")
            response = requests.get(url, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # API 응답 구조: OpenAptInfo -> row
                if 'OpenAptInfo' in data:
                    result = data['OpenAptInfo']
                    
                    # 총 데이터 개수 확인
                    total_count = result.get('list_total_count', 0)
                    if start_index == 1:
                        print(f"   전체 데이터: {total_count}건")
                    
                    if 'row' in result:
                        df = pd.DataFrame(result['row'])
                        print(f"✅ {len(df)}개의 아파트 정보를 수집했습니다.")
                        return df
                    else:
                        print("⚠️ 데이터가 없습니다.")
                        return pd.DataFrame()
                else:
                    print(f"⚠️ API 응답 구조가 예상과 다릅니다: {list(data.keys())}")
                    return pd.DataFrame()
            else:
                print(f"❌ API 호출 실패: {response.status_code}")
                print(f"   응답: {response.text[:200]}")
                return pd.DataFrame()
                
        except Exception as e:
            print(f"❌ 서울 열린데이터광장 아파트 정보 크롤링 오류: {type(e).__name__}")
            print(f"   오류 내용: {str(e)[:200]}")
            return pd.DataFrame()
    
    def crawl_seoul_apartment_info_all(self, max_records: int = 10000) -> pd.DataFrame:
        """
        서울 열린데이터광장에서 모든 아파트 정보 데이터 크롤링
        (여러 번 호출하여 전체 데이터 수집)
        
        Args:
            max_records: 최대 수집할 레코드 수
        
        Returns:
            pd.DataFrame: 전체 아파트 정보 데이터프레임
        """
        all_data = []
        start_index = 1
        batch_size = 1000
        
        print(f"서울 열린데이터광장에서 최대 {max_records}개의 아파트 정보를 수집합니다...")
        
        while start_index <= max_records:
            end_index = min(start_index + batch_size - 1, max_records)
            df_batch = self.crawl_seoul_apartment_info(start_index, end_index)
            
            if df_batch.empty:
                print("더 이상 데이터가 없습니다.")
                break
            
            all_data.append(df_batch)
            start_index = end_index + 1
            
            # API 호출 제한을 위한 지연
            time.sleep(CRAWL_DELAY)
            
            if len(df_batch) < batch_size:
                print("마지막 배치를 수집했습니다.")
                break
        
        if all_data:
            result_df = pd.concat(all_data, ignore_index=True)
            print(f"\n✅ 총 {len(result_df)}개의 아파트 정보를 수집했습니다.")
            return result_df
        else:
            print("❌ 수집된 데이터가 없습니다.")
            return pd.DataFrame()
    
    def process_seoul_apartment_info_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        서울 열린데이터광장에서 수집한 아파트 정보 데이터를 앱에서 사용할 형식으로 변환
        
        Args:
            df: 원본 데이터프레임
        
        Returns:
            pd.DataFrame: 변환된 데이터프레임
        """
        if df.empty:
            return df
        
        processed_data = []
        
        for _, row in df.iterrows():
            # 명세서에 따른 필드 매핑
            # APT_NM: k-아파트명
            apt_name = row.get('APT_NM', '') or ''
            
            # APT_RDN_ADDR: kapt도로명주소
            address = row.get('APT_RDN_ADDR', '') or ''
            
            # SGG_ADDR: 주소(시군구) - 자치구
            district = row.get('SGG_ADDR', '') or ''
            
            # USE_APRV_YMD: k-사용검사일-사용승인일 (준공일자)
            completion_date = row.get('USE_APRV_YMD', None)
            build_year = None
            if completion_date and pd.notna(completion_date):
                try:
                    # 날짜 형식: "2003-12-26 00:00:00.0"
                    date_str = str(completion_date)
                    if len(date_str) >= 4:
                        build_year = int(date_str[:4])
                except:
                    pass
            
            # TNOHSH: k-전체세대수
            households = row.get('TNOHSH', None)
            try:
                households = int(households) if pd.notna(households) else None
            except:
                households = None
            
            # ROAD_TYPE: k-복도유형 (복도식, 계단식, 혼합식)
            road_type = row.get('ROAD_TYPE', '') or ''
            hallway_type = None
            if road_type:
                if '복도' in str(road_type):
                    hallway_type = "복도식"
                elif '계단' in str(road_type):
                    hallway_type = "계단식"
                elif '혼합' in str(road_type):
                    hallway_type = "혼합식"
                else:
                    hallway_type = str(road_type)  # 원본 값 유지
            
            # RSDT_XUAR: k-주거전용면적 (제곱미터)
            area_sqm = row.get('RSDT_XUAR', None)
            try:
                area_sqm = float(area_sqm) if pd.notna(area_sqm) else None
            except:
                area_sqm = None
            
            pyeong = calculate_pyeong(area_sqm) if area_sqm else None
            
            # YCRD: 좌표Y (위도), XCRD: 좌표X (경도)
            lat = row.get('YCRD', None)  # 위도
            lon = row.get('XCRD', None)  # 경도
            
            # 지하철역 거리 계산
            nearest_station = None
            distance_km = None
            if lat and lon and pd.notna(lat) and pd.notna(lon):
                try:
                    nearest_station, distance_km = calculate_distance_to_subway(float(lat), float(lon))
                except:
                    pass
            
            # BLDR: k-건설사(시공사)
            builder = row.get('BLDR', '') or ''
            
            # DVLR: k-시행사
            developer = row.get('DVLR', '') or ''
            
            # MN_MTHD: k-난방방식
            heating_method = row.get('MN_MTHD', '') or ''
            
            # HMPG: k-홈페이지
            homepage = row.get('HMPG', '') or ''
            
            # 세대당 평균 전용면적 계산 (전체 단지 전용면적 / 세대수)
            avg_area_per_household = None
            avg_pyeong_per_household = None
            if area_sqm and households and households > 0:
                try:
                    avg_area_per_household = round(area_sqm / households, 2)
                    avg_pyeong_per_household = calculate_pyeong(avg_area_per_household)
                except:
                    pass
            
            # PRK_CNTOM: 주차대수
            parking_count = row.get('PRK_CNTOM', None)
            try:
                parking_count = int(parking_count) if pd.notna(parking_count) else None
            except:
                parking_count = None
            
            # 세대당 주차 면 갯수 계산
            parking_per_household = None
            if parking_count and households and households > 0:
                try:
                    parking_per_household = round(parking_count / households, 2)
                except:
                    pass
            
            # 전용면적별 세대현황 정보
            # XUAR_HH_STTS60: k-전용면적별세대현황(60㎡이하)
            hh_60sqm = row.get('XUAR_HH_STTS60', None)
            try:
                hh_60sqm = float(hh_60sqm) if pd.notna(hh_60sqm) else None
            except:
                hh_60sqm = None
            
            # XUAR_HH_STTS85: k-전용면적별세대현황(60m²~85m²이하)
            hh_85sqm = row.get('XUAR_HH_STTS85', None)
            try:
                hh_85sqm = float(hh_85sqm) if pd.notna(hh_85sqm) else None
            except:
                hh_85sqm = None
            
            # XUAR_HH_STTS135: k-85m²~135m²이하
            hh_135sqm = row.get('XUAR_HH_STTS135', None)
            try:
                hh_135sqm = float(hh_135sqm) if pd.notna(hh_135sqm) else None
            except:
                hh_135sqm = None
            
            # 원본 데이터를 모두 보존하면서 필요한 파생변수만 추가
            apartment = {
                # === 파생/변환된 컬럼 (앱에서 사용하기 편한 형식) ===
                "자치구": district,
                "주소": address,
                "아파트명": apt_name,
                "건축연도": build_year,
                "세대수": households,
                "복도계단식": hallway_type,
                
                # 면적 정보 (원본 + 파생)
                "전용면적_제곱미터": area_sqm,  # 전체 단지 전용면적 합계 (원본)
                "평형": pyeong,  # 전체 단지 평형 합계 (파생)
                "세대당평균전용면적_제곱미터": avg_area_per_household,  # 세대당 평균 전용면적 (파생)
                "세대당평균평형": avg_pyeong_per_household,  # 세대당 평균 평형 (파생)
                
                # 전용면적별 세대현황
                "전용면적60㎡이하_세대수": hh_60sqm,
                "전용면적60_85㎡_세대수": hh_85sqm,
                "전용면적85_135㎡_세대수": hh_135sqm,
                
                # 주차 정보
                "주차대수": parking_count,  # 주차 대수 (원본)
                "세대당주차면수": parking_per_household,  # 세대당 주차 면 갯수 (파생)
                
                # 위치 정보
                "위도": lat,
                "경도": lon,
                "가장가까운지하철역": nearest_station,
                "지하철역거리_km": distance_km,
                
                # 추가 정보
                "건설사": builder,
                "시행사": developer,
                "난방방식": heating_method,
                "홈페이지": homepage,
                
                # === 원본 API 응답 컬럼 모두 보존 ===
                "원본_SN": row.get('SN', None),
                "원본_APT_CD": row.get('APT_CD', ''),
                "원본_APT_NM": row.get('APT_NM', ''),
                "원본_CMPX_CLSF": row.get('CMPX_CLSF', ''),  # 단지분류
                "원본_APT_STDG_ADDR": row.get('APT_STDG_ADDR', ''),  # 지번주소
                "원본_APT_RDN_ADDR": row.get('APT_RDN_ADDR', ''),  # 도로명주소
                "원본_CTPV_ADDR": row.get('CTPV_ADDR', ''),  # 시도주소
                "원본_SGG_ADDR": row.get('SGG_ADDR', ''),  # 시군구주소
                "원본_EMD_ADDR": row.get('EMD_ADDR', ''),  # 읍면동주소
                "원본_DADDR": row.get('DADDR', ''),  # 상세주소
                "원본_RDN_ADDR": row.get('RDN_ADDR', ''),  # 도로명
                "원본_ROAD_DADDR": row.get('ROAD_DADDR', ''),  # 도로명상세주소
                "원본_TELNO": row.get('TELNO', ''),
                "원본_FXNO": row.get('FXNO', ''),  # 팩스번호
                "원본_APT_CMPX": row.get('APT_CMPX', ''),  # 아파트단지
                "원본_APT_ATCH_FILE": row.get('APT_ATCH_FILE', ''),  # 첨부파일
                "원본_HH_TYPE": row.get('HH_TYPE', ''),  # 세대유형
                "원본_MNG_MTHD": row.get('MNG_MTHD', ''),  # 관리방법
                "원본_ROAD_TYPE": row.get('ROAD_TYPE', ''),  # 복도유형
                "원본_MN_MTHD": row.get('MN_MTHD', ''),  # 난방방식
                "원본_WHOL_DONG_CNT": row.get('WHOL_DONG_CNT', None),  # 전체동수
                "원본_TNOHSH": row.get('TNOHSH', None),  # 전체세대수
                "원본_BLDR": row.get('BLDR', ''),  # 건설사
                "원본_DVLR": row.get('DVLR', ''),  # 시행사
                "원본_USE_APRV_YMD": row.get('USE_APRV_YMD', ''),  # 사용승인일
                "원본_GFA": row.get('GFA', None),  # 연면적
                "원본_RSDT_XUAR": row.get('RSDT_XUAR', None),  # 주거전용면적
                "원본_MNCO_LEVY_AREA": row.get('MNCO_LEVY_AREA', None),  # 관리비부과면적
                "원본_XUAR_HH_STTS60": row.get('XUAR_HH_STTS60', None),  # 전용면적별세대현황(60㎡이하)
                "원본_XUAR_HH_STTS85": row.get('XUAR_HH_STTS85', None),  # 전용면적별세대현황(60㎡~85㎡이하)
                "원본_XUAR_HH_STTS135": row.get('XUAR_HH_STTS135', None),  # 85㎡~135㎡이하
                "원본_XUAR_HH_STTS136": row.get('XUAR_HH_STTS136', None),  # 135㎡초과
                "원본_HMPG": row.get('HMPG', ''),  # 홈페이지
                "원본_REG_YMD": row.get('REG_YMD', ''),  # 등록일자
                "원본_MDFCN_YMD": row.get('MDFCN_YMD', ''),  # 수정일자
                "원본_EPIS_MNG_NO": row.get('EPIS_MNG_NO', ''),  # 에피소드관리번호
                "원본_EPS_MNG_FORM": row.get('EPS_MNG_FORM', ''),  # 에피소드관리형태
                "원본_HH_ELCT_CTRT_MTHD": row.get('HH_ELCT_CTRT_MTHD', ''),  # 세대전기계약방법
                "원본_CLNG_MNG_FORM": row.get('CLNG_MNG_FORM', ''),  # 냉방관리형태
                "원본_BDAR": row.get('BDAR', None),  # 건물면적
                "원본_PRK_CNTOM": row.get('PRK_CNTOM', None),  # 주차대수
                "원본_SE_CD": row.get('SE_CD', ''),  # 시설코드
                "원본_CMPX_APRV_DAY": row.get('CMPX_APRV_DAY', ''),  # 단지승인일
                "원본_USE_YN": row.get('USE_YN', ''),  # 사용여부
                "원본_MNCO_ULD_YN": row.get('MNCO_ULD_YN', ''),  # 관리사무소유무
                "원본_XCRD": row.get('XCRD', ''),  # 경도
                "원본_YCRD": row.get('YCRD', ''),  # 위도
                "원본_CMPX_APLD_DAY": row.get('CMPX_APLD_DAY', ''),  # 단지적용일
            }
            
            processed_data.append(apartment)
        
        return pd.DataFrame(processed_data)
    
    def download_seoul_apartment_csv_selenium(self) -> str:
        """
        Selenium을 사용하여 서울 열린데이터광장에서 CSV 파일 자동 다운로드
        (로그인 필요 시 작동하지 않을 수 있음)
        
        Returns:
            str: 다운로드된 파일 경로 또는 None
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.chrome.options import Options
            import os
            import time
            import glob
            
            print("=" * 60)
            print("Selenium을 사용한 자동 다운로드 시도")
            print("=" * 60)
            
            # Chrome 옵션 설정
            chrome_options = Options()
            chrome_options.add_argument('--headless')  # 백그라운드 실행
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            
            # 다운로드 경로 설정
            download_dir = os.getcwd()
            prefs = {
                "download.default_directory": download_dir,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True
            }
            chrome_options.add_experimental_option("prefs", prefs)
            
            print("Chrome 드라이버 초기화 중...")
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                from selenium.webdriver.chrome.service import Service
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
            except:
                # webdriver-manager가 없으면 기본 경로 사용
                driver = webdriver.Chrome(options=chrome_options)
            
            try:
                url = "https://data.seoul.go.kr/dataList/OA-15818/S/1/datasetView.do"
                print(f"페이지 접속: {url}")
                driver.get(url)
                
                time.sleep(3)  # 페이지 로드 대기
                
                # CSV 다운로드 버튼 찾기
                print("CSV 다운로드 버튼 찾는 중...")
                
                # 여러 가능한 선택자 시도
                selectors = [
                    "a[href*='csv']",
                    "a[href*='download']",
                    "button[onclick*='csv']",
                    ".download",
                    "#download",
                ]
                
                download_clicked = False
                for selector in selectors:
                    try:
                        element = WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                        print(f"다운로드 요소 발견: {selector}")
                        element.click()
                        download_clicked = True
                        break
                    except:
                        continue
                
                if not download_clicked:
                    print("⚠️  다운로드 버튼을 찾을 수 없습니다.")
                    print("   페이지 소스 확인 중...")
                    page_source = driver.page_source
                    if 'csv' in page_source.lower() or 'download' in page_source.lower():
                        print("   CSV 관련 요소가 페이지에 있지만 자동 클릭 실패")
                    driver.quit()
                    return None
                
                # 다운로드 완료 대기
                print("다운로드 완료 대기 중...")
                time.sleep(10)
                
                # 다운로드된 파일 찾기
                downloaded_files = glob.glob(os.path.join(download_dir, "*.csv"))
                if downloaded_files:
                    # 가장 최근 파일
                    latest_file = max(downloaded_files, key=os.path.getctime)
                    print(f"✅ 다운로드 완료: {latest_file}")
                    driver.quit()
                    return latest_file
                else:
                    print("⚠️  다운로드된 파일을 찾을 수 없습니다.")
                    driver.quit()
                    return None
                    
            except Exception as e:
                print(f"❌ 다운로드 오류: {type(e).__name__}")
                print(f"   오류 내용: {str(e)[:200]}")
                driver.quit()
                return None
                
        except ImportError:
            print("❌ Selenium이 설치되지 않았습니다.")
            print("   설치: pip install selenium")
            return None
        except Exception as e:
            print(f"❌ Selenium 초기화 오류: {type(e).__name__}")
            print(f"   오류 내용: {str(e)[:200]}")
            return None
    
    def download_seoul_apartment_csv(self) -> str:
        """
        서울 열린데이터광장에서 아파트 메타데이터 CSV 파일 다운로드 시도
        (실제로는 다운로드 링크를 찾아서 안내)
        
        Returns:
            str: 다운로드된 파일 경로 또는 None
        """
        import os
        import requests
        from bs4 import BeautifulSoup
        
        print("=" * 60)
        print("서울 열린데이터광장 CSV 다운로드 시도")
        print("=" * 60)
        
        url = "https://data.seoul.go.kr/dataList/OA-15818/S/1/datasetView.do"
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # CSV 다운로드 링크 찾기
                # 서울 열린데이터광장은 보통 JavaScript로 다운로드 처리
                # 직접 다운로드 URL을 찾기 어려울 수 있음
                
                print("⚠️  자동 다운로드가 어렵습니다.")
                print("   서울 열린데이터광장은 로그인이 필요하거나")
                print("   JavaScript로 다운로드를 처리할 수 있습니다.")
                print("\n📥 수동 다운로드 방법:")
                print("   1. https://data.seoul.go.kr/dataList/OA-15818/S/1/datasetView.do 접속")
                print("   2. '파일내려받기' 또는 'CSV 다운로드' 버튼 클릭")
                print("   3. 다운로드한 파일을 프로젝트 폴더에 저장")
                
                return None
            else:
                print(f"❌ 페이지 접속 실패: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ 다운로드 시도 오류: {type(e).__name__}")
            print(f"   오류 내용: {str(e)[:200]}")
            return None
    
    def crawl_seoul_apartment_info_from_web(self, max_pages: int = 100) -> pd.DataFrame:
        """
        서울 열린데이터광장 웹사이트에서 아파트 메타데이터 크롤링
        미리보기 페이지에서 데이터를 수집합니다.
        
        ⚠️ 주의: 웹 크롤링은 사이트 정책을 확인하고 사용하세요.
        미리보기는 최대 1,000건까지 노출됩니다.
        
        Args:
            max_pages: 최대 수집할 페이지 수
        
        Returns:
            pd.DataFrame: 아파트 정보 데이터프레임
        """
        print("=" * 60)
        print("서울 열린데이터광장 웹 크롤링 시작")
        print("=" * 60)
        print("⚠️  웹 크롤링은 사이트 정책을 확인하고 사용하세요.")
        print("    미리보기는 최대 1,000건까지 노출됩니다.")
        print("    전체 데이터는 CSV 파일 다운로드를 권장합니다.")
        print("=" * 60)
        
        all_data = []
        
        try:
            # 서울 열린데이터광장 미리보기 API 엔드포인트 시도
            # 실제 엔드포인트는 사이트 구조에 따라 다를 수 있음
            base_url = "https://data.seoul.go.kr/dataList/OA-15818/S/1/datasetView.do"
            
            # 대안: CSV 파일이 이미 있다면 로드
            print("\n💡 권장: CSV 파일을 직접 다운로드하여 사용하세요:")
            print("   https://data.seoul.go.kr/dataList/OA-15818/S/1/datasetView.do")
            print("   페이지에서 '파일내려받기' 또는 'CSV 다운로드' 클릭")
            print("\n   다운로드한 파일을 load_seoul_csv_file()로 로드하세요.")
            
            return pd.DataFrame()
            
        except Exception as e:
            print(f"❌ 웹 크롤링 오류: {type(e).__name__}")
            print(f"   오류 내용: {str(e)[:200]}")
            return pd.DataFrame()
    
    def crawl_seoul_apartment_info_all_with_csv(self, csv_file_path: str = None) -> pd.DataFrame:
        """
        CSV 파일을 사용하여 아파트 메타데이터 전체 수집
        CSV 파일이 없으면 다운로드 안내
        
        Args:
            csv_file_path: CSV 파일 경로 (None이면 자동 검색)
        
        Returns:
            pd.DataFrame: 처리된 아파트 정보 데이터프레임
        """
        import os
        import glob
        
        print("=" * 60)
        print("CSV 파일을 통한 아파트 메타데이터 수집")
        print("=" * 60)
        
        # CSV 파일 찾기
        if csv_file_path is None:
            # 일반적인 파일명 패턴 검색
            possible_files = [
                "*.csv",
                "*아파트*.csv",
                "*apartment*.csv",
                "*OA-15818*.csv",
            ]
            
            found_files = []
            for pattern in possible_files:
                found_files.extend(glob.glob(pattern))
            
            if found_files:
                csv_file_path = found_files[0]
                print(f"✅ CSV 파일 발견: {csv_file_path}")
            else:
                print("❌ CSV 파일을 찾을 수 없습니다.")
                print("\n📥 CSV 파일 다운로드 방법:")
                print("   1. https://data.seoul.go.kr/dataList/OA-15818/S/1/datasetView.do 접속")
                print("   2. '파일내려받기' 또는 'CSV 다운로드' 클릭")
                print("   3. 다운로드한 파일을 프로젝트 폴더에 저장")
                print("   4. 다시 실행하거나 load_seoul_csv_file()로 직접 로드")
                return pd.DataFrame()
        
        if not os.path.exists(csv_file_path):
            print(f"❌ 파일을 찾을 수 없습니다: {csv_file_path}")
            return pd.DataFrame()
        
        # CSV 파일 로드 및 처리
        print(f"\n📂 CSV 파일 로드 중: {csv_file_path}")
        df = self.load_seoul_csv_file(csv_file_path)
        
        if df.empty:
            print("❌ CSV 파일이 비어있거나 로드할 수 없습니다.")
            return pd.DataFrame()
        
        print(f"✅ {len(df)}건의 데이터를 로드했습니다.")
        
        # 데이터 변환
        print("\n🔄 데이터 변환 중...")
        processed_df = self.process_seoul_apartment_info_data(df)
        
        if not processed_df.empty:
            print(f"✅ 변환 완료! {len(processed_df)}건의 데이터가 처리되었습니다.")
            
            # 저장
            output_file = "seoul_apartments_metadata.csv"
            self.save_to_csv(processed_df, output_file)
            
            print(f"\n💾 최종 데이터 저장: {output_file}")
            print(f"   총 {len(processed_df)}건의 아파트 메타데이터")
            
            return processed_df
        else:
            print("❌ 데이터 변환 실패")
            return pd.DataFrame()
    
    def crawl_naver_real_estate(self, district: str) -> List[Dict]:
        """
        네이버 부동산에서 아파트 정보 크롤링 (샘플 구조)
        실제 크롤링은 웹사이트 구조에 따라 조정 필요
        
        Args:
            district: 자치구명
        
        Returns:
            List[Dict]: 아파트 정보 리스트
        """
        apartments = []
        
        # 실제 크롤링 코드는 네이버 부동산의 robots.txt와 이용약관을 확인 후 작성
        # 여기서는 샘플 데이터 생성 구조만 제공
        print(f"{district} 네이버 부동산 데이터 수집 중...")
        time.sleep(CRAWL_DELAY)
        
        return apartments
    
    def generate_sample_data(self, num_samples: int = 100) -> pd.DataFrame:
        """
        샘플 데이터 생성 (실제 크롤링 전 테스트용)
        
        Args:
            num_samples: 생성할 샘플 수
        
        Returns:
            pd.DataFrame: 아파트 데이터프레임
        """
        import random
        
        districts = SEOUL_DISTRICTS
        hallway_types = ["복도식", "계단식", "혼합식"]
        
        sample_data = []
        
        for i in range(num_samples):
            district = random.choice(districts)
            build_year = random.randint(1980, 2024)
            households = random.randint(100, 2000)
            hallway_type = random.choice(hallway_types)
            
            # 서울시 내 랜덤 좌표 생성
            lat = random.uniform(37.4, 37.7)
            lon = random.uniform(126.8, 127.2)
            
            # 평형 계산 (전용면적 기준)
            area_sqm = random.uniform(50, 150)
            pyeong = calculate_pyeong(area_sqm)
            
            # 지하철역 거리 계산
            nearest_station, distance_km = calculate_distance_to_subway(lat, lon)
            
            apartment = {
                "자치구": district,
                "주소": f"서울특별시 {district} {random.choice(['로', '길'])} {random.randint(1, 999)}",
                "건축연도": build_year,
                "세대수": households,
                "복도계단식": hallway_type,
                "전용면적_제곱미터": round(area_sqm, 2),
                "평형": pyeong,
                "위도": round(lat, 6),
                "경도": round(lon, 6),
                "가장가까운지하철역": nearest_station,
                "지하철역거리_km": distance_km
            }
            
            sample_data.append(apartment)
        
        return pd.DataFrame(sample_data)
    
    def save_to_csv(self, df: pd.DataFrame, filename: str = "seoul_apartments.csv"):
        """
        데이터를 CSV 파일로 저장
        
        Args:
            df: 저장할 데이터프레임
            filename: 파일명
        """
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"데이터가 {filename}에 저장되었습니다. (총 {len(df)}개)")
    
    def load_from_csv(self, filename: str = "seoul_apartments.csv") -> pd.DataFrame:
        """
        CSV 파일에서 데이터 로드
        
        Args:
            filename: 파일명
        
        Returns:
            pd.DataFrame: 로드된 데이터프레임
        """
        try:
            df = pd.read_csv(filename, encoding='utf-8-sig')
            print(f"{filename}에서 {len(df)}개의 데이터를 로드했습니다.")
            return df
        except FileNotFoundError:
            print(f"{filename} 파일을 찾을 수 없습니다.")
            return pd.DataFrame()
    
    def load_seoul_csv_file(self, csv_file_path: str) -> pd.DataFrame:
        """
        서울 열린데이터광장에서 다운로드한 CSV 파일을 로드하고 처리
        
        Args:
            csv_file_path: CSV 파일 경로
        
        Returns:
            pd.DataFrame: 처리된 데이터프레임
        """
        try:
            print(f"CSV 파일 로드 중: {csv_file_path}")
            df = pd.read_csv(csv_file_path, encoding='utf-8-sig')
            print(f"✅ {len(df)}개의 데이터를 로드했습니다.")
            
            # 데이터 변환
            processed_df = self.process_seoul_real_estate_data(df)
            
            return processed_df
        except FileNotFoundError:
            print(f"❌ 파일을 찾을 수 없습니다: {csv_file_path}")
            return pd.DataFrame()
        except Exception as e:
            print(f"❌ CSV 파일 로드 오류: {type(e).__name__}")
            print(f"   오류 내용: {str(e)[:200]}")
            return pd.DataFrame()


if __name__ == "__main__":
    crawler = SeoulApartmentCrawler()
    
    # API 키 테스트
    print("=" * 50)
    print("API 키 테스트 중...")
    print("=" * 50)
    api_valid = crawler.test_api_key()
    print()
    
    if api_valid:
        print("공공데이터 API를 사용할 수 있습니다.")
    else:
        print("API 키에 문제가 있거나, 샘플 데이터를 사용합니다.")
    
    print("\n" + "=" * 60)
    print("서울 열린데이터광장 데이터 크롤링")
    print("=" * 60)
    print("\n📋 데이터셋 정보:")
    print("  1. OA-15818: 서울시 공동주택 아파트 정보 (메타데이터)")
    print("     - 아파트명, 주소, 준공일자, 세대수, 세대타입 등")
    print("     - https://data.seoul.go.kr/dataList/OA-15818/S/1/datasetView.do")
    print("\n  2. OA-21275: 서울시 부동산 실거래가 정보")
    print("     - 실거래가, 보증금, 월세, 신고년도 등")
    print("     - https://data.seoul.go.kr/dataList/OA-21275/S/1/datasetView.do")
    print("\n" + "=" * 60)
    
    # 1. 아파트 메타데이터 크롤링 시도 (OA-15818)
    print("\n[1단계] 아파트 메타데이터 수집 시도 (OA-15818)...")
    apartment_info_df = crawler.crawl_seoul_apartment_info_all(max_records=5000)
    
    if not apartment_info_df.empty:
        # 데이터 변환
        processed_df = crawler.process_seoul_apartment_info_data(apartment_info_df)
        
        # CSV로 저장
        crawler.save_to_csv(processed_df, "seoul_apartments_metadata.csv")
        
        print("\n✅ 아파트 메타데이터 수집 완료!")
        print(f"   총 {len(processed_df)}개의 아파트 정보가 저장되었습니다.")
        print("\n수집된 데이터 샘플:")
        print(processed_df.head())
        
        # 메타데이터를 메인 데이터로 사용
        main_df = processed_df
    else:
        print("⚠️  아파트 메타데이터를 API로 수집할 수 없습니다.")
        print("   CSV 파일 다운로드 방식을 사용하세요.")
        main_df = None
    
    # 2. 실거래가 데이터 크롤링 시도 (OA-21275)
    print("\n" + "=" * 60)
    print("[2단계] 부동산 실거래가 데이터 수집 시도 (OA-21275)...")
    real_estate_df = crawler.crawl_seoul_real_estate_all(max_records=5000)
    
    if not real_estate_df.empty:
        # 데이터 변환
        processed_real_estate_df = crawler.process_seoul_real_estate_data(real_estate_df)
        
        # CSV로 저장
        crawler.save_to_csv(processed_real_estate_df, "seoul_real_estate.csv")
        
        print("\n✅ 실거래가 데이터 수집 완료!")
        print(f"   총 {len(processed_real_estate_df)}개의 실거래가 정보가 저장되었습니다.")
        print("\n수집된 데이터 샘플:")
        print(processed_real_estate_df.head())
    else:
        print("⚠️  실거래가 데이터를 API로 수집할 수 없습니다.")
        print("   CSV 파일 다운로드 방식을 사용하세요.")
    
    # 3. 최종 데이터 통합 또는 샘플 데이터 생성
    if main_df is None or main_df.empty:
        print("\n" + "=" * 60)
        print("[3단계] 샘플 데이터 생성...")
        print("=" * 60)
        print("\n⚠️  실제 데이터를 수집할 수 없어 샘플 데이터를 생성합니다.")
        print("   CSV 파일을 다운로드하여 사용하시면 더 정확한 데이터를 얻을 수 있습니다.")
        print("   (CSV_DOWNLOAD_GUIDE.md 참고)")
        
        # 샘플 데이터 생성
        df = crawler.generate_sample_data(num_samples=500)
        
        # CSV로 저장
        crawler.save_to_csv(df, "seoul_apartments.csv")
        
        print("\n✅ 샘플 데이터 생성 완료!")
        print(f"   총 {len(df)}개의 샘플 데이터가 저장되었습니다.")
        print("\n생성된 데이터 샘플:")
        print(df.head())
    else:
        # 메타데이터를 메인 데이터로 사용
        crawler.save_to_csv(main_df, "seoul_apartments.csv")
        print("\n✅ 최종 데이터 저장 완료: seoul_apartments.csv")

