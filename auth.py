"""
실거래 트래커 로그인 (secrets.toml 계정 + session_state)

브라우저 탭의 Streamlit 세션이 유지되는 동안 로그인 상태가 남고,
서버 재시작 시에는 풀립니다. 계정 DB는 쓰지 않습니다.
"""
import hmac

import streamlit as st

SESSION_KEY_TRACKER_USER = "tracker_user"


def _as_user_map(section) -> dict:
    if not section:
        return {}
    try:
        return {str(k).strip(): str(v) for k, v in dict(section).items() if k is not None and v is not None}
    except (TypeError, ValueError):
        return {}


def get_tracker_users() -> dict:
    """
    secrets에서 허용 계정(아이디=비밀번호)을 읽습니다.

    지원 형식:
      [tracker_users]
      mom = "password"

      [secrets.tracker_users]
      mom = "password"
    """
    try:
        secrets = getattr(st, "secrets", None)
        if not secrets:
            return {}
    except Exception:
        return {}

    try:
        nested = secrets["secrets"]["tracker_users"]
        users = _as_user_map(nested)
        if users:
            return users
    except (KeyError, TypeError, AttributeError):
        pass

    try:
        users = _as_user_map(secrets["tracker_users"])
        if users:
            return users
    except (KeyError, TypeError, AttributeError):
        pass

    return {}


def get_tracker_user() -> str:
    user = st.session_state.get(SESSION_KEY_TRACKER_USER)
    if not user:
        return ""
    return str(user).strip()


def is_tracker_logged_in() -> bool:
    user = get_tracker_user()
    if not user:
        return False
    return user in get_tracker_users()


def login_tracker(username: str, password: str) -> bool:
    users = get_tracker_users()
    user = (username or "").strip()
    pw = "" if password is None else str(password)
    expected = users.get(user)
    if expected is None:
        return False
    if not hmac.compare_digest(str(expected).encode("utf-8"), pw.encode("utf-8")):
        return False
    st.session_state[SESSION_KEY_TRACKER_USER] = user
    return True


def logout_tracker() -> None:
    st.session_state.pop(SESSION_KEY_TRACKER_USER, None)


def render_tracker_login_panel(title="로그인", prefix="app") -> None:
    """앱 진입 전 로그인 폼을 그립니다."""
    st.subheader(title)
    st.caption("허용된 계정으로 로그인한 뒤 메뉴를 사용할 수 있습니다.")
    users = get_tracker_users()

    if not users:
        st.warning("secrets.toml의 `[tracker_users]`에 계정을 추가하면 로그인할 수 있습니다.")
        return

    with st.form(f"{prefix}_login_form", clear_on_submit=True):
        username = st.text_input("아이디", key=f"{prefix}_login_id")
        password = st.text_input("비밀번호", type="password", key=f"{prefix}_login_pw")
        if st.form_submit_button("로그인", use_container_width=True):
            if login_tracker(username, password):
                st.rerun()
            else:
                st.error("아이디 또는 비밀번호가 올바르지 않습니다.")


def render_app_login() -> None:
    _, mid, _ = st.columns([1, 1.15, 1])
    with mid:
        render_tracker_login_panel("서울 아파트 검색", "app")
