"""
유틸리티 함수들
"""
from geopy.distance import geodesic
from subway_stations import SUBWAY_STATIONS


def calculate_distance_to_subway(lat, lon):
    """
    아파트 위치에서 가장 가까운 지하철역과의 직선 거리 계산 (km)
    
    Args:
        lat: 위도
        lon: 경도
    
    Returns:
        tuple: (가장 가까운 역 이름, 거리(km))
    """
    if not lat or not lon:
        return None, None
    
    try:
        apt_location = (lat, lon)
        min_distance = float('inf')
        nearest_station = None
        
        for station_name, station_coords in SUBWAY_STATIONS.items():
            distance = geodesic(apt_location, station_coords).kilometers
            if distance < min_distance:
                min_distance = distance
                nearest_station = station_name
        
        return nearest_station, round(min_distance, 2)
    except Exception as e:
        print(f"거리 계산 오류: {e}")
        return None, None


def extract_district(address):
    """
    주소에서 자치구 추출
    
    Args:
        address: 전체 주소 문자열
    
    Returns:
        str: 자치구명
    """
    if not address:
        return None
    
    districts = [
        "강남구", "강동구", "강북구", "강서구", "관악구", "광진구", "구로구", "금천구",
        "노원구", "도봉구", "동대문구", "동작구", "마포구", "서대문구", "서초구", "성동구",
        "성북구", "송파구", "양천구", "영등포구", "용산구", "은평구", "종로구", "중구", "중랑구"
    ]
    
    for district in districts:
        if district in address:
            return district
    
    return None


def extract_dong(address):
    """
    주소에서 동 추출 (도로명 주소에서 동 정보 추출 시도)
    
    Args:
        address: 전체 주소 문자열
    
    Returns:
        str: 동명 (없으면 None)
    """
    if not address:
        return None
    
    # float나 다른 타입이 들어올 수 있으므로 문자열로 변환
    try:
        address = str(address)
    except:
        return None
    
    if not address or address == 'nan' or address == 'None':
        return None
    
    import re
    # "서울특별시 자치구 동명" 패턴 찾기
    # 도로명 주소에서는 동 정보가 직접 포함되지 않을 수 있음
    # "XX동" 패턴 찾기
    dong_pattern = r'(\w+동)'
    match = re.search(dong_pattern, address)
    if match:
        return match.group(1)
    
    # 주소를 공백으로 분리하여 자치구 다음 단어가 동일 수 있음
    # 하지만 도로명 주소에서는 동 정보가 없을 수 있음
    return None


def calculate_pyeong(area_sqm):
    """
    제곱미터를 평형으로 변환
    
    Args:
        area_sqm: 제곱미터
    
    Returns:
        float: 평형 (소수점 첫째자리)
    """
    if not area_sqm:
        return None
    try:
        pyeong = float(area_sqm) / 3.3058
        return round(pyeong, 1)
    except:
        return None

