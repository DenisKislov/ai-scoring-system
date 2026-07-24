"""Streamlit UI for the candidate-scoring system.

Run from the project root: ``streamlit run ui/app.py``.

Flow (matches the ТЗ MVP): pick a vacancy -> "Рассчитать" -> ranked table
"позиция | Score | навыки | ранг" -> pick a candidate -> resume text with
matched skills highlighted -> HR feedback buttons (Релевантен / Нерелевантен).

The UI talks to MongoDB and the scorer directly (no FastAPI layer yet), so it
is a faithful MVP of the product rather than a mockup.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st  # noqa: E402

from db import mongo  # noqa: E402
from db.builders import resume_text  # noqa: E402
from scorer.service import score_vacancy  # noqa: E402
from ui.highlight import highlight_skills  # noqa: E402

TOP_N = 50


def _vacancy_card(vacancy_id: str) -> None:
    vac = mongo.get_vacancy(vacancy_id)
    if not vac:
        return
    st.caption("Вакансия")
    st.markdown(f"#### {vac.get('title') or '(без названия)'}")
    skills = vac.get("skills") or []
    if skills:
        st.markdown(" ".join(f"`{s}`" for s in skills))
    desc = (vac.get("description") or "").strip()
    if desc:
        with st.expander("Описание вакансии"):
            st.write(desc[:1500] + ("…" if len(desc) > 1500 else ""))


def _results_table(results: list) -> None:
    rows = []
    for i, r in enumerate(results[:TOP_N]):
        rows.append(
            {
                "#": i + 1,
                "Позиция": r.get("position") or "(резюме)",
                "Score": r["score"],
                "Опыт": r.get("experience_years") if r.get("experience_years") is not None else "—",
                "keyword": round(r["keyword_score"], 2),
                "cosine": round(r["cosine_sim"], 2),
                "Навыки": ", ".join(r.get("matched_skills", [])) or "—",
                "Ранг %": r.get("rank_percentile"),
            }
        )
    st.dataframe(rows, use_container_width=True, height=320, hide_index=True)


def _candidate_detail(results: list, vacancy_id: str) -> None:
    choices = list(range(min(len(results), TOP_N)))
    sel = st.selectbox(
        "Кандидат для деталей",
        choices,
        format_func=lambda i: f"#{i+1}  Score {results[i]['score']}  —  {results[i].get('position') or '(резюме)'}",
    )
    cand = results[sel]
    rid = cand["candidate_id"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Score", cand["score"])
    m2.metric("keyword", f"{cand['keyword_score']:.2f}")
    m3.metric("cosine", f"{cand['cosine_sim']:.2f}")
    years = cand.get("experience_years")
    m4.metric("Опыт (лет)", years if years is not None else "—")

    missing = cand.get("missing_skills", [])
    if missing:
        st.caption("⚠️ Отсутствуют: " + ", ".join(missing))

    rdoc = mongo.get_resume(rid)
    rtxt = resume_text(rdoc) if rdoc else "(текст резюме недоступен)"
    st.markdown("**Резюме** (найденные навыки подсвечены):")
    st.markdown(highlight_skills(rtxt, cand.get("matched_skills", [])), unsafe_allow_html=True)

    st.markdown("**Решение HR** (Да/Нет — для будущего дообучения):")
    existing = mongo.get_feedback(vacancy_id, rid)
    b1, b2, b3 = st.columns([1, 1, 2])
    if b1.button("✅ Релевантен", use_container_width=True):
        mongo.save_feedback(vacancy_id, rid, "yes")
        st.toast("Сохранено: релевантен")
        st.rerun()
    if b2.button("❌ Нерелевантен", use_container_width=True):
        mongo.save_feedback(vacancy_id, rid, "no")
        st.toast("Сохранено: нерелевантен")
        st.rerun()
    if existing:
        b3.info(f"Текущее решение: {'✅ Релевантен' if existing == 'yes' else '❌ Нерелевантен'}")
    else:
        b3.caption("Решение ещё не принято")


def main() -> None:
    st.set_page_config(page_title="AI-скоринг кандидатов", page_icon="🎯", layout="wide")
    st.title("🎯 AI-скоринг кандидатов")
    st.caption("Ранжирование резюме под вакансию · keyword + TF-IDF/cosine · MongoDB")

    vacancies = mongo.list_vacancies()
    if not vacancies:
        st.warning("В БД нет вакансий. Запустите парсер или `python -m db.seed`.")
        st.stop()

    labels = {v["_id"]: (v.get("title") or "(без названия)") for v in vacancies}
    with st.sidebar:
        st.header("Параметры")
        vid = st.selectbox("Вакансия", list(labels.keys()), format_func=lambda i: labels[i])
        limit = st.slider("Резюме в пуле", 5, 100, 50, step=5)
        run = st.button("Рассчитать скоринг", type="primary", use_container_width=True)

    if run:
        with st.spinner("Скоринг пула резюме…"):
            out = score_vacancy(vid, limit_resumes=limit)
        st.session_state["results"] = out["results"]
        st.session_state["vacancy_id"] = vid

    results = st.session_state.get("results")
    vacancy_id = st.session_state.get("vacancy_id") or vid

    if not results:
        st.info("👈 Выберите вакансию и нажмите «Рассчитать скоринг».")
        _vacancy_card(vid)
        st.stop()

    _vacancy_card(vacancy_id)
    st.subheader(f"Топ-{min(len(results), TOP_N)} кандидатов")
    _results_table(results)
    st.divider()
    _candidate_detail(results, vacancy_id)


if __name__ == "__main__":
    main()
