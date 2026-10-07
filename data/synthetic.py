"""Seeded evaluation data with latent candidate ability and noisy documents.

The generated relevance is calculated from abilities, role fit and experience
*before* the resume text is rendered. A candidate may know an unmentioned skill,
and a vacancy lists only a plausible subset of its profession's stack.
"""
from __future__ import annotations

import random
from typing import Dict, List

from faker import Faker

from .profiles import ROLE_KEYS, ROLES, render_resume, render_vacancy

ADJACENT_ROLES = {
    "Python-разработчик": ("Data Engineer", "QA-инженер", "DevOps-инженер"),
    "Data Scientist": ("Data Engineer", "Python-разработчик"),
    "Frontend-разработчик": ("QA-инженер", "Python-разработчик"),
    "DevOps-инженер": ("Data Engineer", "Python-разработчик"),
    "QA-инженер": ("Frontend-разработчик", "Python-разработчик"),
    "Data Engineer": ("Data Scientist", "DevOps-инженер", "Python-разработчик"),
}


def generate_vacancy(profession: str, rng: random.Random, faker: Faker) -> Dict:
    if profession not in ROLES:
        raise ValueError(f"Unknown profession: {profession}")
    stack = ROLES[profession]["skills"]
    required = rng.sample(stack, k=rng.randint(6, min(9, len(stack) - 2)))
    critical = rng.sample(required, k=2)
    remaining = [skill for skill in stack if skill not in required]
    optional = rng.sample(remaining, k=min(rng.randint(1, 3), len(remaining)))
    years = rng.randint(1, 5)
    return {
        "role": profession,
        "skills": required,
        "critical_skills": critical,
        "optional_skills": optional,
        "required_years": years,
        "text": render_vacancy(
            profession, required, rng, optional_skills=optional,
            critical_skills=critical, required_years=years,
        ),
    }


def _candidate_role(vacancy_role: str, target_fit: float, rng: random.Random) -> str:
    adjacent = ADJACENT_ROLES[vacancy_role]
    unrelated = [role for role in ROLE_KEYS if role != vacancy_role and role not in adjacent]
    draw = rng.random()
    if target_fit >= 0.65:
        same_p, adjacent_p = 0.75, 0.25
    elif target_fit >= 0.30:
        same_p, adjacent_p = 0.30, 0.50
    else:
        same_p, adjacent_p = 0.06, 0.29
    if draw < same_p:
        return vacancy_role
    if draw < same_p + adjacent_p or not unrelated:
        return rng.choice(adjacent)
    return rng.choice(unrelated)


def _relevance(vacancy: Dict, skills: set[str], role: str, years: int) -> tuple[float, dict]:
    required = set(vacancy["skills"])
    critical = set(vacancy["critical_skills"])
    coverage = len(skills & required) / len(required) if required else 0.0
    critical_coverage = len(skills & critical) / len(critical) if critical else 0.0
    role_fit = (1.0 if role == vacancy["role"] else
                0.6 if role in ADJACENT_ROLES[vacancy["role"]] else 0.2)
    experience_fit = min(years / vacancy["required_years"], 1.0)
    # Defined on latent abilities, not on words visible to the scorer.
    relevance = (0.55 * coverage + 0.20 * critical_coverage +
                 0.15 * role_fit + 0.10 * experience_fit)
    return round(relevance, 3), {
        "required_skill_coverage": round(coverage, 3),
        "critical_skill_coverage": round(critical_coverage, 3),
        "role_fit": role_fit,
        "experience_fit": round(experience_fit, 3),
    }


def generate_resume(
    vacancy: Dict, overlap: float, rng: random.Random, faker: Faker
) -> Dict:
    """Build one profile; ``overlap`` controls a broad difficulty band only."""
    target_fit = min(1.0, max(0.0, overlap))
    profession = _candidate_role(vacancy["role"], target_fit, rng)
    role_stack = ROLES[profession]["skills"]
    latent = set(rng.sample(role_stack, k=rng.randint(5, min(10, len(role_stack)))))

    # Shared tools and career transitions create partial matches across roles.
    for skill in vacancy["skills"]:
        if profession == vacancy["role"]:
            chance = 0.12 + 0.72 * target_fit
        elif profession in ADJACENT_ROLES[vacancy["role"]]:
            chance = 0.05 + 0.55 * target_fit
        else:
            chance = 0.02 + 0.15 * target_fit
        if rng.random() < chance:
            latent.add(skill)
    if rng.random() < 0.35:
        neighboring = rng.choice(ADJACENT_ROLES[profession])
        latent.update(rng.sample(ROLES[neighboring]["skills"], k=rng.randint(1, 2)))

    years = rng.randint(0, 10)
    truth, components = _relevance(vacancy, latent, profession, years)

    # Real CVs omit familiar tools. Text is a noisy view of the latent profile.
    disclosure = (rng.uniform(0.30, 0.48) if rng.random() < 0.15
                  else rng.uniform(0.55, 0.85))
    visible = [skill for skill in sorted(latent) if rng.random() < disclosure]
    if not visible:
        visible = [rng.choice(sorted(latent))]
    rng.shuffle(visible)
    # Course-only familiarity is mentioned in a CV but does not imply the
    # professional ability used for the relevance label.
    familiar_pool = [skill for skill in role_stack if skill not in latent]
    familiar = (rng.sample(familiar_pool, k=min(rng.randint(1, 2), len(familiar_pool)))
                if familiar_pool and rng.random() < 0.30 else [])
    return {
        "text": render_resume(profession, visible, rng, faker,
                              years=years, familiar_skills=familiar),
        "true_relevance": truth,
        "role": profession,
        "skills": sorted(latent),
        "text_skills": visible + familiar,
        "familiar_only_skills": familiar,
        "experience_years": years,
        "relevance_components": components,
    }


def generate_dataset(
    n_vacancies: int = 6, n_resumes: int = 20, seed: int = 42
) -> List[Dict]:
    if n_vacancies < 1 or n_resumes < 1:
        raise ValueError("n_vacancies and n_resumes must be positive")
    rng = random.Random(seed)
    faker = Faker("ru_RU")
    faker.seed_instance(seed)

    dataset: List[Dict] = []
    for index in range(n_vacancies):
        profession = ROLE_KEYS[index % len(ROLE_KEYS)]
        vacancy = generate_vacancy(profession, rng, faker)
        # Stratified difficulty guarantees informative positives and negatives,
        # while the actual relevance is measured after a stochastic profile draw.
        weak_count = n_resumes // 2
        mixed_count = (3 * n_resumes) // 10
        bands = ([(0.02, 0.27)] * weak_count +
                 [(0.27, 0.65)] * mixed_count +
                 [(0.65, 0.98)] * (n_resumes - weak_count - mixed_count))
        rng.shuffle(bands)
        candidates = [generate_resume(vacancy, rng.uniform(low, high), rng, faker)
                      for low, high in bands]
        rng.shuffle(candidates)
        dataset.append({"vacancy": vacancy, "candidates": candidates})
    return dataset
