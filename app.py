"""
울산과학대학교 + 고등교육 법령 AI 규정 검색 시스템
"""
import os
import io
import re
import datetime
import markdown as md_lib
import streamlit as st
import requests
from bs4 import BeautifulSoup
import anthropic
from urllib.parse import urljoin
from law_data import search_laws
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

load_dotenv()

# ── 색상 (UC CI + 보조) ──────────────────────────────────────────────────────
NAVY          = "#1B3A5C"   # 사이드바·강조 (딥 네이비)
NAVY_DARK     = "#122840"   # 사이드바 진한
NAVY_PALE     = "#EDF2F7"   # 연한 배경
TEAL          = "#007B6E"   # UC Green (태그·링크 등 포인트)
GRAY_TEXT     = "#4A4A4A"
GRAY_BG       = "#F6F6F6"   # 답변 배경 (아주 연한 회색)

UC_REGULATION_URL = "https://www.uc.ac.kr/www/CMS/RegulationBookMgr/list.do?mCode=MN055"
# 흰 배경에 맞는 로고 (문자형 시그니처 PNG)
UC_LOGO_URL = "https://www.uc.ac.kr/resources/homepage/www/_Img/Contents/ci_logo1_1.png"

MAJOR_LAWS = [
    "고등교육법", "고등교육법 시행령", "고등교육법 시행규칙",
    "교육기본법", "사립학교법", "대학설립·운영 규정", "교원지위법",
]

SYSTEM_PROMPT = """당신은 울산과학대학교 대학 행정 전문 AI입니다. 총장·보직교수의 의사결정을 지원합니다.

답변 형식을 반드시 지키세요:

**[결론]**
핵심 답변을 2~3문장으로 먼저 제시.

**[근거 조항]**
관련 조문을 아래 형식으로 하나씩 인용:
▶ 법령명 제N조(제목): "조문 원문을 그대로 인용"
▶ 규정명 제N조(제목): "조문 원문을 그대로 인용"

**[실무 해석]**
조문의 의미와 실제 적용 방법을 구체적으로 설명. 애매하거나 해석이 엇갈릴 수 있는 부분은 명확히 짚어줌.

**[추가 검토 필요 사항]**
이 사안과 관련해 추가로 확인해야 할 조문·규정·상황을 2~3가지 제시. 논의가 필요한 쟁점도 포함.

규칙:
- 불확실한 내용은 "확인 필요"로 표시
- 조문 원문이 없으면 "해당 조문 원문 확인 필요"로 명시
- 한국어, 결론 먼저, 빈말 금지"""


# ── CSS ──────────────────────────────────────────────────────────────────────
def inject_css():
    st.markdown(f"""
<style>
.stApp {{ background: #F4F5F7; }}
header[data-testid="stHeader"] {{ background: transparent; }}

[data-testid="stSidebar"] {{ background: {NAVY_DARK}; }}
[data-testid="stSidebar"] * {{ color: #C8D8E8 !important; }}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{ color: #FFFFFF !important; }}
[data-testid="stSidebar"] .stButton button {{
    background: rgba(255,255,255,0.12); color: white !important;
    border: 1px solid rgba(255,255,255,0.25); border-radius: 6px;
}}
[data-testid="stSidebar"] .stButton button:hover {{ background: rgba(255,255,255,0.2); }}
[data-testid="stSidebar"] input {{
    background: rgba(255,255,255,0.1) !important;
    color: white !important;
    border: 1px solid rgba(255,255,255,0.2) !important;
}}
[data-testid="stSidebar"] a {{ color: #90BCD8 !important; }}

.stButton > button[kind="primary"] {{
    background: {NAVY}; border: none; border-radius: 8px;
    font-weight: 600; letter-spacing: 0.02em; color: white;
}}
.stButton > button[kind="primary"]:hover {{ background: {NAVY_DARK}; }}

.stTextInput input {{
    border: 1.5px solid #C8D0DA; border-radius: 8px;
    font-size: 1rem; background: white;
}}
.stTextInput input:focus {{
    border-color: {NAVY}; box-shadow: 0 0 0 3px rgba(27,58,92,0.1);
}}

.reg-card {{
    background: white; border-left: 4px solid {TEAL};
    border-radius: 0 10px 10px 0; padding: 0.85rem 1.1rem;
    margin: 0.4rem 0; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}}
.reg-card a {{ color: {NAVY}; text-decoration: none; font-weight: 600; font-size: 0.93rem; }}
.reg-card a:hover {{ text-decoration: underline; }}

.law-card {{
    background: white; border-left: 4px solid {NAVY};
    border-radius: 0 10px 10px 0; padding: 0.85rem 1.1rem;
    margin: 0.4rem 0; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}}
.law-title {{ font-weight: 700; font-size: 0.9rem; color: {NAVY}; margin-bottom: 0.35rem; }}
.law-content {{
    background: #F0F4F8; border-radius: 6px; padding: 0.6rem 0.85rem;
    font-size: 0.83rem; line-height: 1.65; color: #333;
    margin-top: 0.35rem; border-left: 3px solid #B0C4D8;
}}
.law-link {{ font-size: 0.74rem; color: {TEAL}; text-decoration: none; float: right; }}

.tag {{
    display: inline-block; font-size: 0.69rem; background: #EBF0F6;
    color: {NAVY}; border-radius: 4px; padding: 0.1rem 0.45rem;
    margin-bottom: 0.35rem; font-weight: 600; letter-spacing: 0.02em;
}}
.tag-teal {{ background: #E4F2F0; color: {TEAL}; }}

.bubble-user {{
    background: {NAVY_PALE}; border: 1px solid #C8D4E0;
    border-radius: 14px 14px 4px 14px; padding: 0.65rem 1rem;
    margin: 0.8rem 0 0.3rem 0; font-size: 0.92rem;
    font-weight: 600; color: {NAVY};
}}
.bubble-ai {{
    background: #F7F7F7; border: 1px solid #E4E4E4;
    border-radius: 0 0 10px 10px; padding: 1.1rem 1.4rem;
    margin: 0 0 1rem 0; font-size: 0.9rem;
    line-height: 1.65; color: #222;
}}
/* 답변 내부 마크다운 스타일 */
.bubble-ai h1, .bubble-ai h2, .bubble-ai h3 {{
    font-size: 0.92rem; font-weight: 700; color: {NAVY};
    margin: 1rem 0 0.3rem 0; padding-bottom: 0.2rem;
    border-bottom: 1px solid #DDE2E8;
}}
.bubble-ai p {{ margin: 0.3rem 0; }}
.bubble-ai ul, .bubble-ai ol {{ margin: 0.3rem 0 0.3rem 1.2rem; padding: 0; }}
.bubble-ai li {{ margin: 0.15rem 0; }}
.bubble-ai strong {{ color: {NAVY}; }}
.bubble-ai blockquote {{
    border-left: 3px solid {TEAL}; margin: 0.5rem 0;
    padding: 0.3rem 0.8rem; background: #F0F4F8; color: #444;
    font-size: 0.87rem;
}}
.bubble-ai table {{
    width: 100%; border-collapse: collapse;
    font-size: 0.85rem; margin: 0.6rem 0;
}}
.bubble-ai th {{
    background: {NAVY}; color: white; padding: 0.45rem 0.7rem;
    text-align: left; font-weight: 600;
}}
.bubble-ai td {{
    padding: 0.4rem 0.7rem; border-bottom: 1px solid #E5E5E5;
    vertical-align: top;
}}
.bubble-ai tr:nth-child(even) td {{ background: #F7F8FA; }}

.section-header {{
    font-size: 0.78rem; font-weight: 700; color: #7A8A9A;
    letter-spacing: 0.1em; text-transform: uppercase;
    margin: 1.1rem 0 0.45rem 0; padding-bottom: 0.3rem;
    border-bottom: 1.5px solid #DDE2E8;
}}

.stDownloadButton button {{
    background: white; border: 1.5px solid {NAVY};
    color: {NAVY}; border-radius: 8px; font-weight: 600;
}}
.stDownloadButton button:hover {{ background: {NAVY_PALE}; }}

hr {{ border-color: #DDE2E8; margin: 1.4rem 0; }}
</style>
""", unsafe_allow_html=True)


# ── PDF 생성 ─────────────────────────────────────────────────────────────────
def generate_pdf(query: str, chat_history: list, law_results: list, regulations: list) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm
    )

    # 폰트: 시스템 한글 폰트 시도
    font_name = "Helvetica"
    for path in [
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/NanumGothic.ttf",
        "C:/Windows/Fonts/gulim.ttc",
    ]:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("KorFont", path))
                font_name = "KorFont"
            except Exception:
                pass
            break

    uc_green = colors.HexColor("#007B6E")
    uc_dark  = colors.HexColor("#005A52")
    gray_bg  = colors.HexColor("#F5F5F5")

    styles = getSampleStyleSheet()
    style_title   = ParagraphStyle("title",   fontName=font_name, fontSize=16, textColor=uc_dark,  spaceAfter=4, leading=22)
    style_sub     = ParagraphStyle("sub",     fontName=font_name, fontSize=9,  textColor=colors.HexColor("#888888"), spaceAfter=12)
    style_section = ParagraphStyle("section", fontName=font_name, fontSize=11, textColor=uc_green, spaceBefore=12, spaceAfter=4, fontWeight="BOLD")
    style_q       = ParagraphStyle("q",       fontName=font_name, fontSize=10, textColor=uc_dark,  spaceBefore=8, spaceAfter=4, leftIndent=10, borderPad=6, backColor=colors.HexColor("#E8F5F3"), borderColor=colors.HexColor("#B8DDD9"), borderWidth=1, borderRadius=4)
    style_a       = ParagraphStyle("a",       fontName=font_name, fontSize=9,  textColor=colors.HexColor("#222222"), spaceBefore=4, spaceAfter=8, leftIndent=0, leading=15)
    style_law     = ParagraphStyle("law",     fontName=font_name, fontSize=9,  textColor=colors.HexColor("#1A4A5C"), spaceBefore=4, spaceAfter=2, leftIndent=10)
    style_lawbody = ParagraphStyle("lawbody", fontName=font_name, fontSize=8,  textColor=colors.HexColor("#444444"), leftIndent=20, spaceAfter=6, leading=13)
    style_note    = ParagraphStyle("note",    fontName=font_name, fontSize=7.5, textColor=colors.HexColor("#999999"), spaceAfter=0)

    now = datetime.datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
    story = []

    # 헤더
    story.append(Paragraph("울산과학대학교 규정 검색 결과", style_title))
    story.append(Paragraph(f"검색어: {query}  |  생성일시: {now}", style_sub))
    story.append(HRFlowable(width="100%", thickness=2, color=uc_green, spaceAfter=10))

    # 관련 법령
    if law_results:
        story.append(Paragraph("■ 관련 상위 법령", style_section))
        for item in law_results:
            story.append(Paragraph(f"<b>{item['law']} {item['article']} ({item['title']})</b>", style_law))
            story.append(Paragraph(item['content'], style_lawbody))

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CCCCCC"), spaceAfter=8))

    # AI 질의응답
    story.append(Paragraph("■ AI 분석 및 질의응답", style_section))
    turns = []
    if len(chat_history) >= 2:
        turns.append(("Q", query, chat_history[1]["content"]))
    for i in range(2, len(chat_history), 2):
        user_msg = chat_history[i]["content"]
        ai_msg   = chat_history[i+1]["content"] if i+1 < len(chat_history) else ""
        turns.append(("Q", user_msg, ai_msg))

    for idx, (_, q_text, a_text) in enumerate(turns, 1):
        story.append(Paragraph(f"Q{idx}. {q_text}", style_q))
        # 줄바꿈 처리
        for line in a_text.split("\n"):
            line = line.strip()
            if line:
                # ** 마크다운 → <b> 변환 (정규식으로 쌍 매칭)
                safe = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', line)
                # XML 특수문자 이스케이프 (태그 제외)
                safe = safe.replace("&", "&amp;").replace("<b>", "\x00B\x00").replace("</b>", "\x00/B\x00")
                safe = safe.replace("<", "&lt;").replace(">", "&gt;")
                safe = safe.replace("\x00B\x00", "<b>").replace("\x00/B\x00", "</b>")
                try:
                    story.append(Paragraph(safe, style_a))
                except Exception:
                    story.append(Paragraph(line[:200], style_a))
        story.append(Spacer(1, 4))

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CCCCCC"), spaceAfter=6))
    story.append(Paragraph("※ 본 문서는 AI 분석 결과로 참고용입니다. 중요한 결정 전 원문 규정을 반드시 확인하세요.", style_note))

    doc.build(story)
    return buf.getvalue()


# ── 유틸 ─────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="대학 규정집 불러오는 중…")
def fetch_uc_regulations():
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(UC_REGULATION_URL, headers=headers, timeout=10)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        regulations = []
        for row in soup.select("table tr, .board-list li"):
            title_el = row.select_one("td a, li a")
            if title_el:
                title = title_el.get_text(strip=True)
                href  = title_el.get("href", "")
                if href:
                    regulations.append({"title": title, "url": urljoin("https://www.uc.ac.kr", href)})
        return regulations or _default_regs()
    except Exception:
        return _default_regs()


def _default_regs():
    return [
        {"title": "울산과학대학교 학칙",    "url": UC_REGULATION_URL},
        {"title": "학사운영규정",            "url": UC_REGULATION_URL},
        {"title": "교원인사규정",            "url": UC_REGULATION_URL},
        {"title": "학생생활규정",            "url": UC_REGULATION_URL},
        {"title": "장학금 운영규정",         "url": UC_REGULATION_URL},
        {"title": "산학협력 규정",           "url": UC_REGULATION_URL},
        {"title": "교원징계규정",            "url": UC_REGULATION_URL},
        {"title": "회계규정",                "url": UC_REGULATION_URL},
    ]


def build_context(regulations, law_results):
    reg_ctx = "\n".join([f"- {r['title']}" for r in regulations[:8]])
    law_ctx = "\n".join([
        f"- {i['law']} {i['article']} ({i['title']}): {i['content']}"
        for i in law_results
    ])
    return f"[울산과학대학교 관련 규정]\n{reg_ctx}\n\n[관련 법령 조문 전문]\n{law_ctx}"


def render_answer(text: str) -> str:
    """마크다운 → HTML 변환 (표·굵기·목록 포함)"""
    html = md_lib.markdown(
        text,
        extensions=["tables", "nl2br", "fenced_code"],
    )
    return html


def chat_with_claude(messages, api_key):
    if not api_key:
        return "⚠️ Claude API 키를 사이드바에 입력해주세요."
    client = anthropic.Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        return resp.content[0].text
    except anthropic.AuthenticationError:
        return "❌ Claude API 키가 올바르지 않습니다."
    except Exception as e:
        return f"❌ 오류: {str(e)}"


# ── 앱 시작 ──────────────────────────────────────────────────────────────────
st.set_page_config(page_title="UC 규정나침반", page_icon=None, layout="wide")
inject_css()

# 세션 초기화
for key, val in [("chat_history", []), ("context", ""), ("current_query", ""),
                 ("law_results", []), ("matched_regs", [])]:
    if key not in st.session_state:
        st.session_state[key] = val

# ── 사이드바 ─────────────────────────────────────────────────────────────────
with st.sidebar:
    # 로고: 흰 배경 없이 어두운 사이드바 위에 표시 — 국문 로고타입 PNG
    st.markdown(f"""
<div style="padding: 0.5rem 0 0.2rem 0;">
  <img src="{UC_LOGO_URL}" style="width:160px; filter: brightness(0) invert(1);" />
</div>
<div style="font-size:0.8rem; color:#90A8C0; letter-spacing:0.06em; margin-bottom:0.8rem;">
  규정나침반
</div>
""", unsafe_allow_html=True)
    st.markdown("---")

    env_key = os.getenv("ANTHROPIC_API_KEY", "")
    claude_key = st.text_input(
        "Claude API 키",
        value=env_key,
        type="password",
        placeholder="sk-ant-...",
    )

    st.markdown("---")
    st.markdown("**데이터 소스**")
    st.markdown("- 울산과학대학교 전자규정집")
    st.markdown("- 고등교육 법령 (내장)")
    st.markdown("- Claude AI 분석" if claude_key else "- Claude AI (키 필요)")

    st.markdown("---")
    st.markdown("**주요 법령 원문**")
    for law in MAJOR_LAWS:
        url = f"https://www.law.go.kr/법령/{law.replace(' ', '%20')}"
        st.markdown(f"[{law}]({url})")

    st.markdown("---")
    if st.button("대화 초기화", use_container_width=True):
        for key in ["chat_history", "context", "current_query", "law_results", "matched_regs"]:
            st.session_state[key] = [] if key != "context" and key != "current_query" else ""
        st.rerun()

# ── 메인 헤더 ────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="margin-bottom:0.3rem;">
  <div style="font-size:1.6rem; font-weight:800; color:{NAVY_DARK}; letter-spacing:-0.02em;">
    UC 규정나침반
  </div>
  <div style="font-size:0.84rem; color:#7A8A9A; margin-top:3px;">
    울산과학대학교 규정집 · 고등교육 법령 통합 검색 및 AI 질의응답
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ── 검색 영역 ────────────────────────────────────────────────────────────────
col1, col2 = st.columns([4, 1])
with col1:
    query = st.text_input("", placeholder="예: 교원 징계 절차는?  /  장학금 지급 기준은?  /  학칙 개정 절차는?",
                          label_visibility="collapsed", key="search_input")
with col2:
    search_btn = st.button("검색", use_container_width=True, type="primary")

# 빠른 질문
st.markdown('<div class="section-header">자주 찾는 질문</div>', unsafe_allow_html=True)
qcols = st.columns(4)
quick_qs = ["교원 임용 절차", "학생 징계 기준", "장학금 지급 규정", "학칙 개정 절차"]
for i, qq in enumerate(quick_qs):
    if qcols[i].button(qq, use_container_width=True, key=f"quick_{i}"):
        query = qq
        search_btn = True

st.markdown("---")

# ── 검색 실행 ────────────────────────────────────────────────────────────────
if search_btn and query:
    regulations = fetch_uc_regulations()
    keywords = query.split()
    matched = [r for r in regulations if any(k in r["title"] for k in keywords)] or regulations[:6]
    law_results = search_laws(query)

    if query != st.session_state.current_query:
        st.session_state.chat_history  = []
        st.session_state.current_query = query
        st.session_state.context       = build_context(matched, law_results)
        st.session_state.matched_regs  = matched
        st.session_state.law_results   = law_results

    # 패널
    col_l, col_r = st.columns([1, 1])
    with col_l:
        st.markdown('<div class="section-header">관련 대학 규정</div>', unsafe_allow_html=True)
        for r in matched[:6]:
            st.markdown(f"""
<div class="reg-card">
  <span class="tag">전자규정집</span><br>
  <a href="{r['url']}" target="_blank">{r['title']} ↗</a>
</div>""", unsafe_allow_html=True)

    with col_r:
        st.markdown('<div class="section-header">관련 상위 법령</div>', unsafe_allow_html=True)
        if law_results:
            for item in law_results:
                law_url = f"https://www.law.go.kr/법령/{item['law'].replace(' ', '%20')}"
                st.markdown(f"""
<div class="law-card">
  <span class="tag tag-blue">{item['law']}</span>
  <a href="{law_url}" target="_blank" class="law-link">{item['article']} 원문 ↗</a>
  <div class="law-title">{item['article']} {item['title']}</div>
  <div class="law-content">{item['content']}</div>
</div>""", unsafe_allow_html=True)
        else:
            st.info("관련 법령 조문을 찾지 못했습니다.")

    st.markdown("---")

    # 첫 AI 답변
    if not st.session_state.chat_history:
        first_msg = f"{st.session_state.context}\n\n[질문]\n{query}"
        with st.spinner("조문 분석 중…"):
            answer = chat_with_claude([{"role": "user", "content": first_msg}], claude_key or "")
        st.session_state.chat_history = [
            {"role": "user",      "content": first_msg},
            {"role": "assistant", "content": answer},
        ]

# ── 대화 표시 ────────────────────────────────────────────────────────────────
if st.session_state.chat_history:
    st.markdown('<div class="section-header">AI 분석 · 질의응답</div>', unsafe_allow_html=True)

    # PDF 버튼
    pdf_col, _ = st.columns([1, 3])
    with pdf_col:
        try:
            pdf_bytes = generate_pdf(
                st.session_state.current_query,
                st.session_state.chat_history,
                st.session_state.law_results,
                st.session_state.matched_regs,
            )
            fname = f"UC_규정검색_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
            st.download_button("PDF로 저장", data=pdf_bytes, file_name=fname,
                               mime="application/pdf", use_container_width=True)
        except Exception as e:
            st.caption(f"PDF 생성 오류: {e}")

    # 첫 번째 Q&A
    first_answer = st.session_state.chat_history[1]["content"] if len(st.session_state.chat_history) > 1 else ""
    st.markdown(f'<div class="bubble-user">Q.&nbsp; {st.session_state.current_query}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="bubble-ai">{render_answer(first_answer)}</div>', unsafe_allow_html=True)

    # 후속 대화
    for i in range(2, len(st.session_state.chat_history), 2):
        user_msg = st.session_state.chat_history[i]["content"]
        ai_msg   = st.session_state.chat_history[i+1]["content"] if i+1 < len(st.session_state.chat_history) else ""
        st.markdown(f'<div class="bubble-user">Q.&nbsp; {user_msg}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="bubble-ai">{render_answer(ai_msg)}</div>', unsafe_allow_html=True)

    # 추가 질문
    st.markdown("---")
    st.markdown('<div class="section-header">추가 질문 · 논의</div>', unsafe_allow_html=True)
    st.caption("애매한 부분, 구체적 상황, 해석 쟁점 등을 이어서 물어보세요.")
    f1, f2 = st.columns([4, 1])
    with f1:
        follow_up = st.text_input("", placeholder="예: 징계 기간 중 급여는 어떻게 되나요? / 소청심사 청구 기간은?",
                                  label_visibility="collapsed", key="followup")
    with f2:
        if st.button("전송 →", use_container_width=True):
            if follow_up:
                st.session_state.chat_history.append({"role": "user", "content": follow_up})
                with st.spinner("검토 중…"):
                    reply = chat_with_claude(st.session_state.chat_history, claude_key or "")
                st.session_state.chat_history.append({"role": "assistant", "content": reply})
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption("⚠️ AI 답변은 참고용입니다. 중요한 결정 전 원문 규정을 반드시 확인하세요.")

elif not st.session_state.chat_history:
    st.markdown(f"""
<div style="text-align:center; padding: 4rem 2rem; color: #AAA;">
  <div style="font-size:2rem; margin-bottom:1rem; color:#C8D4E0;">[ UC 규정나침반 ]</div>
  <div style="font-size:1.1rem; font-weight:600; color:#555; margin-bottom:0.5rem;">
    울산과학대학교 규정 AI 검색
  </div>
  <div style="font-size:0.9rem; line-height:1.8;">
    검색창에 질문을 입력하면<br>
    대학 규정 + 상위 법령 조문 + AI 분석을 한번에 확인할 수 있습니다.
  </div>
</div>
""", unsafe_allow_html=True)
