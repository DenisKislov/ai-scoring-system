"""Synthetic dataset generator with ground-truth relevance.

Because the customer cannot share real resumes (152-ФЗ) and provides no labels,
we generate our own. The key idea is **profession-driven skill sampling**: a
resume's skills are sampled from the dictionary of *its own* profession
(``skills_by_profession.json``), so a "Data Scientist" resume genuinely
contains ML/Python/pandas — never just a stray filler skill.

For a vacancy of profession P_v we produce a relevance spectrum:

* ``overlap >= 0.5`` — a **same-profession** candidate: we sample
  ``round(overlap · N)`` skills from P_v's dictionary. Its true relevance is
  that overlap (high).
* ``overlap  < 0.5`` — a **foreign-profession** candidate: we sample most of
  another profession's skills. Its true relevance is the (small) overlap with
  P_v's skills — usually near zero, but professions that genuinely share
  skills (e.g. Data Scientist vs Computer Vision) correctly get a real boost.

This couples *both* score components to relevance and, crucially, makes the
ranking behave on cross-cutting vacancies (e.g. a C++/Python/CV vacancy ranks
ML/CV people above generic Python backend people).

The written resume text is a **noisy** view of the sampled skills — some known
skills are omitted and a few off-target ones are name-dropped (see
``_noisy_skills``). The scorer therefore has to recover the true rank from an
imperfect observation rather than trivially echoing it, which is what makes the
ranking metric informative instead of a self-test.
"""
from __future__ import annotations

import random
from typing import Dict, List

from faker import Faker

from .profiles import ROLE_KEYS, ROLES, render_resume, render_vacancy


def generate_vacancy(profession: str, rng: random.Random, faker: Faker) -> Dict:
    """A vacancy for *profession* whose requirements are its full skill set."""
    skills = list(ROLES[profession]["skills"])
    return {
        "role": profession,
        "skills": skills,
        "text": render_vacancy(profession, skills, rng),
    }


def _noisy_skills(
    skills: List[str], vacancy: Dict, profession: str, rng: random.Random
) -> List[str]:
    """Realistic resume noise: what is *written* differs from what is *known*.

    Real resumes do not list every skill a candidate has, and they name-drop a
    few off-target ones. We model that by (a) dropping ~15% of the known skills
    from the written text and (b) sprinkling in 0–2 skills from an unrelated
    profession. This deliberately breaks the tautological
    ``keyword_score == true_relevance`` link, so the ranking metric measures
    whether the scorer recovers the true order from a noisy observation — not
    whether the code runs.
    """
    out = list(skills)
    if len(out) > 2:
        # Random per-resume omission rate — a high-relevance candidate that
        # happens to under-write their skills can slip below a lower one. This
        # is what injects real ranking noise (not a fixed fraction).
        drop = round(len(out) * rng.uniform(0.10, 0.35))
        for idx in sorted(rng.sample(range(len(out)), drop), reverse=True):
            out.pop(idx)
    others = [k for k in ROLE_KEYS if k not in (profession, vacancy["role"])]
    if others:
        for _ in range(rng.randint(1, 3)):
            out.append(rng.choice(ROLES[rng.choice(others)]["skills"]))
    rng.shuffle(out)
    return out


def generate_resume(
    vacancy: Dict, overlap: float, rng: random.Random, faker: Faker
) -> Dict:
    """A resume whose skills come from *its own* profession's dictionary.

    ``overlap`` controls the relevance spectrum (see module docstring) and is
    reflected in ``true_relevance`` — the ground-truth label, i.e. the share of
    skills the candidate actually *knows*. The rendered ``text`` is a noisy
    view of those skills (see :func:`_noisy_skills`), so the scorer must work to
    recover the rank, not just echo it.
    """
    vac_skills = vacancy["skills"]
    vac_set = set(vac_skills)

    if overlap >= 0.5:
        # Same profession: sample `overlap` of its (== the vacancy's) skills.
        profession = vacancy["role"]
        n = max(1, round(overlap * len(vac_skills)))
        skills = rng.sample(vac_skills, min(n, len(vac_skills)))
        true_relevance = len(skills) / len(vac_skills) if vac_skills else 0.0
    else:
        # Foreign profession: realistic sample of THAT profession's skills.
        foreign = [k for k in ROLE_KEYS if k != vacancy["role"]]
        profession = rng.choice(foreign)
        prof_skills = ROLES[profession]["skills"]
        lo = max(1, round(0.6 * len(prof_skills)))
        n = rng.randint(lo, len(prof_skills))
        skills = rng.sample(prof_skills, n)
        # True relevance = share of vacancy skills genuinely present.
        true_relevance = len(set(skills) & vac_set) / len(vac_set) if vac_set else 0.0

    # `skills` is the ground truth (what the candidate knows); the text carries
    # only a noisy subset, so the observed keyword score under-shoots it.
    text_skills = _noisy_skills(skills, vacancy, profession, rng)
    return {
        "text": render_resume(profession, text_skills, rng, faker),
        "true_relevance": round(true_relevance, 3),
        "role": profession,
        "skills": skills,
    }


def generate_dataset(
    n_vacancies: int = 6, n_resumes: int = 20, seed: int = 42
) -> List[Dict]:
    """Generate ``n_vacancies`` vacancies, each with ``n_resumes`` labelled resumes.

    Overlaps are spread evenly across [0, 1] so every vacancy's pool contains
    the full relevance spectrum (a balanced ranking task).
    """
    rng = random.Random(seed)
    faker = Faker("ru_RU")
    faker.seed_instance(seed)

    overlaps = [i / (n_resumes - 1) for i in range(n_resumes)] if n_resumes > 1 else [0.5]

    dataset: List[Dict] = []
    for v in range(n_vacancies):
        profession = ROLE_KEYS[v % len(ROLE_KEYS)]
        vacancy = generate_vacancy(profession, rng, faker)
        candidates = [generate_resume(vacancy, o, rng, faker) for o in overlaps]
        rng.shuffle(candidates)  # don't leave them sorted by relevance
        dataset.append({"vacancy": vacancy, "candidates": candidates})
    return dataset
