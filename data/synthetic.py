import random
from typing import Dict, List

from faker import Faker

from .profiles import ROLE_KEYS, ROLES, render_resume, render_vacancy


def generate_vacancy(profession: str, rng: random.Random, faker: Faker) -> Dict:
    skills = list(ROLES[profession]["skills"])
    return {
        "role": profession,
        "skills": skills,
        "text": render_vacancy(profession, skills, rng),
    }


def _noisy_skills(
    skills: List[str], vacancy: Dict, profession: str, rng: random.Random
) -> List[str]:
    out = list(skills)
    if len(out) > 2:
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
    vac_skills = vacancy["skills"]
    vac_set = set(vac_skills)

    if overlap >= 0.5:
        profession = vacancy["role"]
        n = max(1, round(overlap * len(vac_skills)))
        skills = rng.sample(vac_skills, min(n, len(vac_skills)))
        true_relevance = len(skills) / len(vac_skills) if vac_skills else 0.0
    else:
        foreign = [k for k in ROLE_KEYS if k != vacancy["role"]]
        profession = rng.choice(foreign)
        prof_skills = ROLES[profession]["skills"]
        lo = max(1, round(0.6 * len(prof_skills)))
        n = rng.randint(lo, len(prof_skills))
        skills = rng.sample(prof_skills, n)
        true_relevance = len(set(skills) & vac_set) / len(vac_set) if vac_set else 0.0

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
    rng = random.Random(seed)
    faker = Faker("ru_RU")
    faker.seed_instance(seed)

    overlaps = [i / (n_resumes - 1) for i in range(n_resumes)] if n_resumes > 1 else [0.5]

    dataset: List[Dict] = []
    for v in range(n_vacancies):
        profession = ROLE_KEYS[v % len(ROLE_KEYS)]
        vacancy = generate_vacancy(profession, rng, faker)
        candidates = [generate_resume(vacancy, o, rng, faker) for o in overlaps]
        rng.shuffle(candidates)
        dataset.append({"vacancy": vacancy, "candidates": candidates})
    return dataset