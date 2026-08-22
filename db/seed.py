import argparse

from data.synthetic import generate_dataset
from db import mongo


def seed(n_vacancies: int = 6, n_resumes: int = 20, seed: int = 42, clear: bool = False) -> dict:
    db = mongo.get_db()
    if clear:
        db[mongo.COLL_VACANCIES].delete_many({"_synthetic": True})
        db[mongo.COLL_RESUMES].delete_many({"_synthetic": True})
        db[mongo.COLL_SCORES].delete_many({})

    dataset = generate_dataset(n_vacancies, n_resumes, seed)
    n_v = n_r = 0
    for i, entry in enumerate(dataset):
        profession = entry["vacancy"]["role"]
        vac_item = {
            "url": f"https://hh.ru/vacancy/syn_{i}_{profession.replace(' ', '_')}",
            "title": profession,
            "description": entry["vacancy"]["text"],
            "skills": entry["vacancy"]["skills"],
            "author_name": "Synthetic Corp",
            "tags": [],
            "_synthetic": True,
        }
        db[mongo.COLL_VACANCIES].insert_one(vac_item)
        n_v += 1
        target_url = vac_item["url"]

        for j, c in enumerate(entry["candidates"]):
            res_item = {
                "url": f"https://hh.ru/resume/syn_{i}_{j}",
                "title": c["role"],
                "specialization": c["role"],
                "experience": c["text"],
                "skills": c.get("skills", []),
                "tags": [],
                "_synthetic": True,
                "_target_vacancy_url": target_url,
                "_true_relevance": c["true_relevance"],
            }
            db[mongo.COLL_RESUMES].insert_one(res_item)
            n_r += 1

    print(f"Seeded {n_v} vacancies, {n_r} resumes into db '{mongo.MONGO_DB}'.")
    return {"vacancies": n_v, "resumes": n_r}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Seed MongoDB with synthetic data.")
    p.add_argument("--vacancies", type=int, default=6)
    p.add_argument("--resumes", type=int, default=20)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--clear", action="store_true", help="clear database before seeding")
    args = p.parse_args(argv)
    seed(args.vacancies, args.resumes, args.seed, args.clear)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())