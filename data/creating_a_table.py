import json
import csv

# Загружаем вакансии
with open('data/superjob_dataset.json', 'r', encoding='utf-8') as f:
    vacancies = json.load(f)

# Собираем все уникальные навыки
all_skills = set()
for vac in vacancies:
    skills = vac.get('expected_skills', [])
    all_skills.update(skills)

sorted_skills = sorted(all_skills)

# Создаём CSV
with open('data/ground_truth_vacancies.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    
    # id, навык1, навык2, ...
    header = ['id'] + sorted_skills
    writer.writerow(header)

    for vac in vacancies:
        vac_skills = set(vac.get('expected_skills', []))
        clean_id = vac['id'].replace('sj_', '')
        row = [clean_id] + [1 if skill in vac_skills else 0 for skill in sorted_skills]
        writer.writerow(row)

print(f"Строк: {len(vacancies)}")
print(f"Столбцов навыков: {len(sorted_skills)}")