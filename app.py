"""Мозаика Республики — интерактивная историческая рефлексия (Streamlit).

Students: /?view=student  |  Shared screen: /  |  Teacher: /?view=admin
Set ADMIN_PASSWORD in Streamlit Community Cloud Secrets.
"""
from __future__ import annotations

import csv
import hmac
import html
import json
import math
import random
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path

import qrcode
import streamlit as st
import streamlit.components.v1 as components


st.set_page_config(
    page_title="Мозаика Республики | Ататюрк",
    page_icon="🇹🇷",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DB_FILE = Path(__file__).with_name("republic_mosaic.db")
COLS, ROWS, TILE = 15, 10, 75
PIECES_PER_ANSWER = 6
TOTAL_PIECES = COLS * ROWS
MOSAIC_ORDER = list(range(TOTAL_PIECES))
random.Random(1923).shuffle(MOSAIC_ORDER)


@contextmanager
def db():
    connection = sqlite3.connect(DB_FILE, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=20000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db():
    with db() as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS reflections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            answer TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")


def normalize(s: str):
    return " ".join(str(s).split())


def save_answer(name: str, answer: str):
    name, answer = normalize(name), normalize(answer)
    if not (2 <= len(name) <= 40):
        raise ValueError("Атыңызды 2–40 таңба аралығында жазыңыз.")
    if not (5 <= len(answer) <= 240):
        raise ValueError("Жауап кемінде 5, ең көбі 240 таңба болуы керек.")
    with db() as connection:
        connection.execute(
            "INSERT INTO reflections (student_name, answer, created_at) VALUES (?, ?, ?)",
            (name, answer, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )


def get_answers(limit=None):
    with db() as connection:
        if limit is None:
            return connection.execute("SELECT * FROM reflections ORDER BY id ASC").fetchall()
        return connection.execute("SELECT * FROM reflections ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def delete_answer(answer_id: int):
    with db() as connection:
        connection.execute("DELETE FROM reflections WHERE id=?", (answer_id,))


def clear_answers():
    with db() as connection:
        connection.execute("DELETE FROM reflections")


def safe_csv_cell(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def export_csv(rows):
    buff = StringIO()
    writer = csv.writer(buff)
    writer.writerow(["№", "Студент", "Ответ", "Дата и время (UTC)"])
    for item in rows:
        writer.writerow([item["id"], safe_csv_cell(item["student_name"]), safe_csv_cell(item["answer"]), item["created_at"]])
    return buff.getvalue().encode("utf-8-sig")


def get_secret():
    try:
        return str(st.secrets.get("ADMIN_PASSWORD", "")).strip()
    except (OSError, FileNotFoundError, KeyError):
        return ""


def public_urls():
    url = st.context.url.split("?", 1)[0].rstrip("/") + "/"
    return url, url + "?view=student", url + "?view=admin"


def qr_png(url):
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=12, border=2)
    code.add_data(url)
    code.make(fit=True)
    buf = BytesIO()
    code.make_image(fill_color="#192C2F", back_color="#FFFFFF").save(buf, format="PNG")
    return buf.getvalue()


def five_point_star(cx, cy, radius, inner_radius):
    coords = []
    for n in range(10):
        a = n * math.pi / 5
        radius_now = radius if n % 2 == 0 else inner_radius
        coords.append(f"{cx+math.cos(a)*radius_now:.2f},{cy+math.sin(a)*radius_now:.2f}")
    return " ".join(coords)


def mosaic_svg(rows, new_ids=None):
    """Visible red-white flag pieces from real submissions. Unrevealed squares remain dark.

    Returns a standalone SVG (no external images, no embedded scripts).
    """
    new_ids = new_ids or set()
    width, height = COLS * TILE, ROWS * TILE
    unveiled = min(TOTAL_PIECES, len(rows) * PIECES_PER_ANSWER)
    clip_rects, pieces, labels, lines = [], [], [], []
    for tile_position in range(TOTAL_PIECES):
        x = (tile_position % COLS) * TILE
        y = (tile_position // COLS) * TILE
        # Base unrevealed tile design: dark burgundy, fine gold rim.
        shade = "#301922" if (tile_position // COLS + tile_position % COLS) % 2 else "#361E26"
        pieces.append(f'<rect x="{x}" y="{y}" width="{TILE}" height="{TILE}" fill="{shade}"/>')
        lines.append(f'<rect x="{x+.8}" y="{y+.8}" width="{TILE-1.6}" height="{TILE-1.6}" fill="none" stroke="#8E6060" stroke-opacity=".35"/>')

    for seq in range(unveiled):
        tile_position = MOSAIC_ORDER[seq]
        x = (tile_position % COLS) * TILE
        y = (tile_position // COLS) * TILE
        owner = rows[seq // PIECES_PER_ANSWER]
        name = html.escape(str(owner["student_name"]), quote=True)
        note = html.escape(str(owner["answer"]), quote=True)
        clip_rects.append(f'<rect x="{x}" y="{y}" width="{TILE}" height="{TILE}"/>')
        labels.append(
            f'<g class="tile-hit" data-id="{int(owner["id"])}" tabindex="0" role="button" '
            f'aria-label="{name}: {note}">'
            f'<title>{name} — {note}</title>'
            f'<rect x="{x}" y="{y}" width="{TILE}" height="{TILE}" fill="transparent"/>'
            '</g>'
        )
        if int(owner["id"]) in new_ids:
            lines.append(
                f'<rect class="just-opened" x="{x+1.8}" y="{y+1.8}" '
                f'width="{TILE-3.6}" height="{TILE-3.6}" rx="3" '
                'fill="none" stroke="#FFE7A7" stroke-width="4"/>'
            )

    # Red field, white crescent, and white star, clipped to only revealed mosaic pieces.
    # Stylized emblem: designed specifically for classroom use.
    star = five_point_star(751, 374, 104, 43)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'role="img" aria-label="Түркия туының ашылатын мозаикасы">'
        '<defs><clipPath id="unveiled">' + ''.join(clip_rects) + '</clipPath>'
        '<radialGradient id="flag-red" cx="40%" cy="50%" r="80%">'
        '<stop stop-color="#E51B2B"/><stop offset="1" stop-color="#BA061B"/></radialGradient>'
        '</defs>'
        '<rect width="1125" height="750" rx="10" fill="#311B26"/>'
        + ''.join(pieces)
        + '<g clip-path="url(#unveiled)">'
        '<rect width="1125" height="750" fill="url(#flag-red)"/>'
        '<circle cx="419" cy="375" r="175" fill="white"/>'
        '<circle cx="484" cy="375" r="135" fill="url(#flag-red)"/>'
        f'<polygon points="{star}" fill="white"/></g>'
        + ''.join(lines)
        + ''.join(labels)
        + '<rect x="3" y="3" width="1119" height="744" rx="9" fill="none" stroke="#D6AD6D" stroke-width="5"/>'
        '</svg>'
    )


def mosaic_html(rows, new_ids=None):
    """Embed SVG inside HTML iframe: avoids Streamlit sanitizer stripping the diagram."""
    svg = mosaic_svg(rows, new_ids)
    data = {
        str(row["id"]): {"name": str(row["student_name"]), "answer": str(row["answer"])}
        for row in rows
    }
    # Never embed raw user-controlled markup in HTML/JS.
    serialized = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8" />
<style>
  *{{box-sizing:border-box}}
  body{{margin:0;background:transparent;color:#fff;font-family:Arial,sans-serif}}
  .mosaic-display{{width:min(100%, 650px);margin:0 auto}}
  .flag-frame{{background:#24151e;padding:8px;border:2px solid #B78C54;border-radius:18px;
      box-shadow:0 14px 45px #230b1738;position:relative;overflow:hidden}}
  svg{{display:block;width:100%;height:auto;border-radius:9px;}}
  .tile-hit{{cursor:pointer;outline:none}}
  .tile-hit:hover rect,.tile-hit:focus rect{{fill:#fff4;stroke:#FFEDC0;stroke-width:3}}
  .just-opened{{animation:spark 1.2s ease-out 2;pointer-events:none}}
  @keyframes spark{{from{{opacity:1;stroke-width:6}}to{{opacity:0;stroke-width:1}}}}
  #detail{{min-height:60px;display:flex;align-items:center;justify-content:center;text-align:center;
      border:1px solid #B98E58;border-radius:14px;background:#1A2A2B;padding:12px 14px;
      margin-top:10px;gap:10px;color:#EFDDBE;font-size:15px}}
  #detail strong{{color:#fff5e5}}
  #detail .note{{color:#F2E4CE}}
</style></head><body>
  <div class="mosaic-display"><div class="flag-frame">{svg}</div>
  <div id="detail"><span>🖱️ Нажмите на открытый фрагмент мозаики, чтобы увидеть ответ студента</span></div>
  <script>
    const answers={serialized};
    const details=document.getElementById('detail');
    document.querySelectorAll('.tile-hit').forEach(el=>{{
      const show=()=>{{
        const a=answers[el.dataset.id]; if(!a)return;
        details.replaceChildren();
        const n=document.createElement('strong');n.textContent='👤 '+a.name+' — ';
        const t=document.createElement('span');t.className='note';t.textContent=a.answer;
        details.append(n,t);
      }};
      el.addEventListener('click',show);
      el.addEventListener('keydown',event=>{{if(event.key==='Enter'||event.key===' '){{event.preventDefault();show()}}}});
    }});
  </script></div></body></html>"""


STYLE = """<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Playfair+Display:wght@600;700;800&display=swap');
:root {--bg:#F7F2EB;--ink:#203036;--muted:#63716F;--red:#B3142B;--gold:#B78B50;--paper:#FFFCF7;}
.stApp{background:radial-gradient(ellipse 690px 500px at 100% 0,#F1DDD2,transparent),#F7F2EB;color:var(--ink)}
.block-container{max-width:1350px;padding-top:1.2rem;padding-bottom:3rem}
html,body,.stApp,button,input,textarea{font-family:'Manrope','DejaVu Sans',sans-serif}
#MainMenu,footer{visibility:hidden}
[data-testid=stHeader]{background:transparent}
.brand{font-weight:800;color:#8D1631;font-size:1rem;letter-spacing:.06em;margin:10px 0 24px}
.hero{background:linear-gradient(120deg,#1A2C30,#2F4244 60%,#603139);padding:30px 38px;
  border-radius:27px;position:relative;overflow:hidden;box-shadow:0 17px 38px #2a333020;min-height:196px}
.hero:after{content:'1923';position:absolute;right:20px;top:-10px;font:800 12rem 'Playfair Display',serif;color:#ffffff0e;pointer-events:none}
.kicker{font-size:.8rem;letter-spacing:.17em;color:#F1CF93;font-weight:800}
.hero h1{font:800 clamp(2.3rem,4.0vw,4rem)/1.15 'Playfair Display',Georgia,serif;color:#FFF9ED;margin:12px 0}
.hero h1 span{color:#FFCCAE}.hero p{color:#F0E7DA;font-size:1rem;max-width:830px;line-height:1.75;margin:0}
.section-tag{font-size:.78rem;color:#9C784B;letter-spacing:.15em;font-weight:800;margin:23px 0 6px}
.section-title{font:800 clamp(1.65rem,3vw,2.45rem)/1.25 'Playfair Display',serif;color:#25363A;margin:0 0 12px}
.stat{display:flex;gap:10px;flex-wrap:wrap;align-items:center;padding:8px 0 13px;color:#536762;font-weight:700}
.stat b{color:#9B1932;font-size:1.15rem}.live{display:inline-block;padding:6px 12px;border:1px solid #b7d6c0;
  color:#27734b;border-radius:20px;background:#e5f3e8;font-size:.75rem;font-weight:800}
.qr-title{color:#23393A;font-weight:800;font-size:1rem;text-align:center;margin-bottom:8px}
.qr-note{text-align:center;font-size:.81rem;color:#677471;margin-top:5px}
.entry-card{background:#FFFDF9;border:1px solid #E7DDCB;padding:16px 20px;border-radius:19px;
  box-shadow:0 5px 15px #394a4510;margin-bottom:11px}
.entry-name{font-weight:800;color:#A01B34;font-size:.94rem;margin-bottom:7px}
.entry-answer{color:#243437;font-size:1.05rem;line-height:1.6;overflow-wrap:anywhere}
.answer-browser{background:#FFFCF7;border:1px solid #E2D4BE;border-radius:20px;padding:20px 20px 24px;box-shadow:0 8px 22px #394a4510;margin-top:14px;min-height:290px}
.answer-browser-kicker{color:#9C784B;font-size:.76rem;letter-spacing:.12em;font-weight:800;margin-bottom:13px}
.answer-browser-name{font-size:1.22rem;color:#9D1730;font-weight:800;margin-bottom:13px;overflow-wrap:anywhere}
.answer-browser-text{font-size:1.07rem;color:#23353A;line-height:1.75;white-space:pre-wrap;overflow-wrap:anywhere}
.answer-empty{color:#63716F;font-size:.96rem;line-height:1.7;padding:14px 0}
.progress-note{font-weight:700;color:#7A6A5A;font-size:.89rem;margin:9px 0 0}
.hint{background:#fff5e8;border:1px dashed #DDBA87;border-radius:16px;padding:13px 17px;color:#786042;margin:13px 0}
.prompt-box{padding:17px 22px;background:#fff5e7;border:1px solid #EED2A7;border-radius:19px;margin:18px 0 16px;color:#624D38}
.prompt-box strong{display:block;font-size:1.1rem;color:#823348;margin-bottom:5px}
[data-testid=stWidgetLabel] p{font-weight:800;color:#33413F}
[data-testid=stTextInput] input,[data-testid=stTextArea] textarea{background:#fffdf9;border:1.5px solid #D7CBBB;border-radius:13px;color:#1B3033;font-size:1rem}
[data-testid=stFormSubmitButton] button[kind=primary],.stButton button[kind=primary]{background:#B3142B;
 color:#fff;border:0;border-radius:13px;font-weight:800;min-height:3rem}
.stButton button,.stLinkButton a,.stDownloadButton button{border-radius:12px;font-weight:800}
.footer{text-align:center;color:#95765A;letter-spacing:.07em;font-weight:800;margin:25px 0}
@media (max-width:760px){.block-container{padding:.7rem 1rem 2rem}.hero{padding:25px 23px;min-height:unset}.hero:after{font-size:7rem}.hero h1{font-size:2.15rem}}
</style>"""


def header(tag):
    st.markdown(
        f'<div class="brand">🇹🇷 РЕСПУБЛИКА МОЗАИКАСЫ &nbsp; · &nbsp; {html.escape(tag)}</div>',
        unsafe_allow_html=True,
    )


def wall_view(student_url):
    header("ИНТЕРАКТИВНАЯ РЕФЛЕКСИЯ")
    left, right = st.columns([4.3, 1.15], gap="large", vertical_alignment="center")
    with left:
        st.markdown('''<section class="hero"><div class="kicker">✦ ИСТОРИЯ · ТУРЕЦКАЯ РЕСПУБЛИКА</div>
          <h1>Мозаика <span>Республики</span> 🇹🇷</h1>
          <p>Мустафа Кемаль Ататюрк — основатель Турецкой Республики.<br>
          Каждый ответ открывает новые фрагменты общей исторической мозаики.</p></section>''',
          unsafe_allow_html=True)
    with right:
        st.markdown('<div class="qr-title">📱 Сканируй QR-код</div>', unsafe_allow_html=True)
        st.image(qr_png(student_url), use_container_width=True)
        st.link_button("✍️ Оставить ответ", student_url, use_container_width=True)
        st.markdown('<div class="qr-note">Имя + исторический факт или мысль</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-tag">✦ СОЗДАЁМ ИСТОРИЮ ВМЕСТЕ</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Каждый ответ — часть большой картины</div>', unsafe_allow_html=True)

    @st.fragment(run_every="3s")
    def live_mosaic():
        rows = get_answers()
        count = len(rows)
        pieces = min(TOTAL_PIECES, count * PIECES_PER_ANSWER)
        old_ids = st.session_state.get("mosaic_previous_ids")
        current_ids = {int(row["id"]) for row in rows}
        fresh_ids = current_ids - old_ids if old_ids is not None else set()
        st.session_state["mosaic_previous_ids"] = current_ids
        st.markdown(
            f'<div class="stat"><span>👥 Ответов: <b>{count}</b></span><span>🧩 Открыто: <b>{pieces}/{TOTAL_PIECES}</b></span>'
            ' <span class="live">● В ПРЯМОМ ЭФИРЕ · 3 СЕК</span></div>', unsafe_allow_html=True,
        )
        st.progress(pieces / TOTAL_PIECES)
        # Keep the full flag and tile detail visible without cutting them off.
        mosaic_col, answers_col = st.columns([1.95, 1.1], gap="large", vertical_alignment="top")
        with mosaic_col:
            components.html(mosaic_html(rows, fresh_ids), height=530, scrolling=False)
            if count == 0:
                st.markdown('<div class="hint">🧩 Мозаика пока скрыта. Первый ответ откроет первые шесть элементов!</div>', unsafe_allow_html=True)
            elif pieces == TOTAL_PIECES:
                st.success("🎉 Мозаика Республики собрана! Спасибо всем участникам!")
            else:
                st.markdown('<div class="progress-note">✨ Каждый ответ открывает 6 фрагментов общей мозаики.</div>', unsafe_allow_html=True)

        with answers_col:
            st.markdown("### 📜 Ответы студентов")
            if not rows:
                st.markdown('<div class="answer-browser"><div class="answer-empty">💬 Здесь будут появляться ответы. После первой отправки их можно листать кнопками.</div></div>', unsafe_allow_html=True)
            else:
                # Index is stored per browser session; other viewers and students are unaffected.
                follow_latest = st.session_state.get("mosaic_follow_latest", True)
                selected_id = st.session_state.get("mosaic_selected_answer_id")
                ids = [int(row["id"]) for row in rows]
                if follow_latest or selected_id not in ids:
                    current = len(rows) - 1
                else:
                    current = ids.index(selected_id)

                older, middle, newer = st.columns([1.2, .8, 1.2], gap="small", vertical_alignment="center")
                with older:
                    go_older = st.button("◀ Назад", key="mosaic_older", disabled=current == 0, use_container_width=True)
                with newer:
                    go_newer = st.button("Вперёд ▶", key="mosaic_newer", disabled=current == len(rows)-1, use_container_width=True)
                if go_older:
                    current -= 1
                    st.session_state["mosaic_follow_latest"] = False
                if go_newer:
                    current += 1
                    st.session_state["mosaic_follow_latest"] = current == len(rows) - 1
                st.session_state["mosaic_selected_answer_id"] = ids[current]
                with middle:
                    st.markdown(f"<div style='text-align:center;color:#8D2738;font-weight:800;padding:7px 0'>{current+1} / {len(rows)}</div>", unsafe_allow_html=True)

                active = rows[current]
                st.markdown(
                    '<div class="answer-browser">'
                    '<div class="answer-browser-kicker">✦ МЫСЛЬ СТУДЕНТА</div>'
                    f'<div class="answer-browser-name">👤 {html.escape(active["student_name"], quote=True)}</div>'
                    f'<div class="answer-browser-text">{html.escape(active["answer"], quote=True)}</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
                st.caption("← Более ранние ответы · Более новые →")
                if not st.session_state.get("mosaic_follow_latest", True):
                    if st.button("↪ К последнему ответу", key="mosaic_latest", use_container_width=True):
                        st.session_state["mosaic_follow_latest"] = True
                        st.session_state["mosaic_selected_answer_id"] = ids[-1]
                        st.rerun(scope="fragment")

    live_mosaic()
    st.markdown('<div class="footer">✦ 29 ОКТЯБРЯ 1923 · ИСТОРИЧЕСКАЯ ПАМЯТЬ И ЗНАНИЯ ✦</div>', unsafe_allow_html=True)


def student_view(wall_url):
    header("СТРАНИЦА СТУДЕНТА")
    st.markdown('''<div class="hero"><div class="kicker">✦ ТВОЁ МНЕНИЕ ВАЖНО</div>
      <h1>Добавь свою <span>часть мозаики!</span> 🧩</h1>
      <p>Поделись тем, что запомнилось тебе об Ататюрке и создании Турецкой Республики.</p></div>''',
      unsafe_allow_html=True)
    l, r = st.columns([2.1, 1], gap="large")
    with l:
        st.markdown('''<div class="prompt-box"><strong>💭 Вопрос для рефлексии</strong>
         Какой факт, поступок или реформа Мустафы Кемаля Ататюрка запомнились тебе больше всего — и почему?</div>''',
         unsafe_allow_html=True)
        with st.form("reflect_form", clear_on_submit=True):
            name = st.text_input("👤 Твоё имя", placeholder="Например: Амина", max_chars=40)
            answer = st.text_area("✍️ Твой ответ", placeholder="Меня удивило, что ...", max_chars=240, height=138)
            submitted = st.form_submit_button("🧩 Добавить фрагменты мозаики", type="primary", use_container_width=True)
        if submitted:
            try:
                save_answer(name, answer)
            except ValueError as error:
                st.warning(str(error))
            except sqlite3.Error:
                st.error("Не удалось сохранить ответ. Попробуй ещё раз.")
            else:
                st.success(f"✨ Спасибо, {normalize(name)}! Твой ответ открыл шесть новых фрагментов мозаики.")
                st.balloons()
        st.link_button("👀 Посмотреть общую мозаику", wall_url, use_container_width=True)
    with r:
        st.markdown('''<div class="prompt-box"><strong>💡 Можешь начать так:</strong>
         «Я узнал(а), что...»<br>«Меня удивило...»<br>«Самой важной реформой я считаю...»</div>''',
         unsafe_allow_html=True)
        st.info("Твой ответ и имя появятся на экране преподавателя. Пиши уважительно и по теме урока.")


def admin_view(wall_url):
    header("ПАНЕЛЬ ПРЕПОДАВАТЕЛЯ")
    st.title("🔐 Управление мозаикой")
    password = get_secret()
    if not password:
        st.error("Управление выключено: сначала задайте ADMIN_PASSWORD в Streamlit Cloud → Settings → Secrets.")
        st.code('ADMIN_PASSWORD = "ваш-надежный-пароль"', language="toml")
        return
    if not st.session_state.get("mosaic_admin_authenticated", False):
        with st.form("login"):
            supplied = st.text_input("Пароль преподавателя", type="password")
            login = st.form_submit_button("Войти", type="primary")
        if login:
            if hmac.compare_digest(supplied.encode("utf-8"), password.encode("utf-8")):
                st.session_state["mosaic_admin_authenticated"] = True
                st.rerun()
            else:
                st.error("Неверный пароль")
        return

    if st.button("🚪 Выйти из панели"):
        st.session_state["mosaic_admin_authenticated"] = False
        st.rerun()

    rows = get_answers()
    st.metric("Ответов студентов", len(rows))
    st.metric("Открыто фрагментов", f"{min(TOTAL_PIECES, len(rows)*PIECES_PER_ANSWER)} из {TOTAL_PIECES}")
    st.download_button(
        "⬇️ Скачать все ответы (CSV)", data=export_csv(rows),
        file_name="ataturk_republic_mosaic_answers.csv", mime="text/csv", use_container_width=True,
        disabled=not rows,
    )
    st.divider()
    st.subheader("🗑️ Удалить отдельный ответ")
    if rows:
        by_id = {int(row["id"]): row for row in rows}
        picked = st.selectbox("Выберите ответ", list(reversed(by_id)),
            format_func=lambda i: f'#{i} — {by_id[i]["student_name"]}: {by_id[i]["answer"][:70]}')
        if st.button("Удалить выбранный ответ"):
            delete_answer(int(picked))
            st.rerun()
    else:
        st.info("Ответов пока нет.")
    st.divider()
    st.subheader("🧹 Очистить мозаику перед следующим занятием")
    confirmed = st.checkbox("Подтверждаю удаление ВСЕХ ответов")
    if st.button("Очистить всю мозаику", disabled=not confirmed or not rows, type="primary"):
        clear_answers()
        st.rerun()
    st.warning("На бесплатном Streamlit Cloud локальная база SQLite временная. Сохраните CSV перед перезапуском приложения.")
    st.link_button("↗ Открыть экран проектора", wall_url)


def main():
    init_db()
    st.markdown(STYLE, unsafe_allow_html=True)
    wall_url, student_url, _ = public_urls()
    mode = st.query_params.get("view", "wall")
    if mode == "student":
        student_view(wall_url)
    elif mode == "admin":
        admin_view(wall_url)
    else:
        wall_view(student_url)


if __name__ == "__main__":
    main()
