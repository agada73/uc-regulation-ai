import streamlit as st

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.markdown("""
<style>
.stApp { background: #F4F5F7; }
.login-box {
    max-width: 380px;
    margin: 8rem auto;
    background: white;
    border-radius: 12px;
    padding: 2.5rem 2rem;
    box-shadow: 0 4px 20px rgba(0,0,0,0.08);
    text-align: center;
}
.login-title {
    font-size: 1.3rem;
    font-weight: 800;
    color: #122840;
    margin-bottom: 0.3rem;
}
.login-sub {
    font-size: 0.82rem;
    color: #888;
    margin-bottom: 1.5rem;
}
</style>
<div class="login-box">
  <div class="login-title">UC 규정나침반</div>
  <div class="login-sub">울산과학대학교 규정 AI 검색</div>
</div>
""", unsafe_allow_html=True)

    password = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")

    if st.button("로그인", use_container_width=False):
        if password == st.secrets["APP_PASSWORD"]:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("비밀번호가 올바르지 않습니다.")

    return st.session_state.authenticated
