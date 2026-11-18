"""Harder, overlapping IT profiles: one fixed design, no metric-based selection.

This is a diagnostic synthetic corpus, not a re-creation of SuperJob. The same
latent-coverage reference rule as the earlier synthetic corpus is retained.
No extractor/model/scorer imports or calls are used to construct the documents.
"""
from __future__ import annotations

import json
from pathlib import Path
import random

from .dataset import write_controls
from .synthetic_hh import duration, period, write_structured_pdf

VERSION = 'pmi-it-challenging-1'
SEED = 2026111802
PROFILES = {
    'Серверная разработка':('Backend-разработчик',
        ['Python','Django','FastAPI','PostgreSQL','Docker','Git','Redis','pytest']),
    'Аналитика данных':('Аналитик данных',
        ['Python','SQL','pandas','Excel','Power BI','PostgreSQL','A/B-тестирование','Визуализация данных']),
    'Контроль качества':('Инженер по автоматизации тестирования',
        ['Python','pytest','Selenium','Postman','SQL','Git','Docker','REST API']),
    'Эксплуатация':('Инженер эксплуатации',
        ['Linux','Docker','Kubernetes','Git','Ansible','Terraform','Prometheus','PostgreSQL']),
    'Инженерия данных':('Инженер данных',
        ['Python','SQL','PostgreSQL','Airflow','Spark','Kafka','Docker','Git']),
}
NARRATIVES = {
    'Серверная разработка':(
        'Поддержка сервисов приёма заявок и обмена сведениями между приложениями.',
        'Исправление ошибок после выпуска и подготовка изменений по обращениям пользователей.'),
    'Аналитика данных':(
        'Подготовка регулярных показателей для операционной команды.',
        'Сверка источников, поиск расхождений и объяснение изменений в показателях.'),
    'Контроль качества':(
        'Проверка продукта перед выпуском и разбор найденных дефектов.',
        'Подготовка проверок повторяющихся операций и проверка исправлений.'),
    'Эксплуатация':(
        'Сопровождение внутренних площадок и разбор инцидентов доступности.',
        'Подготовка изменений окружения и проверка восстановления после отказа.'),
    'Инженерия данных':(
        'Подготовка потоков обработки и проверка полноты входящих сведений.',
        'Сопровождение регулярных загрузок, контроль ошибок и повторный запуск задач.'),
}
VARIANTS = {
    'Python':['Python','питон','Python 3'],
    'PostgreSQL':['PostgreSQL','Postgres','постгрес'],
    'FastAPI':['FastAPI','Fast API'],
    'Kubernetes':['Kubernetes','k8s'],
    'Power BI':['Power BI','PowerBI'],
    'A/B-тестирование':['A/B-тестирование','A/B тесты'],
    'REST API':['REST API','RESTful API'],
    'Airflow':['Airflow','Apache Airflow'],
    'Spark':['Spark','Apache Spark'],
    'Kafka':['Kafka','Apache Kafka'],
    'Визуализация данных':['Визуализация данных','построение дашбордов'],
}
ACHIEVEMENTS = [
    'После пересмотра порядка проверки уменьшилось число повторных обращений.',
    'Подготовил понятный порядок передачи результатов между участниками команды.',
    'Нашёл причину повторяющегося сбоя и согласовал исправление с ответственными.',
    'Обновил порядок сверки результатов; спорные случаи вынесены на обсуждение.',
]
RENDERED_MENTIONS = [
    'В работе использовал {skill}.',
    'Задачи включали работу с {skill}.',
    'Практический опыт: {skill}.',
    'Применял {skill} при сопровождении решения.',
]


def generate(root: Path):
    rng = random.Random(SEED)
    for kind in ['vacancies','resumes','controls']:
        (root/kind).mkdir(parents=True,exist_ok=True)
    vacancies,resumes = [],[]
    stacks = [set(stack) for _,stack in PROFILES.values()]
    for profile_index,(direction,(role,stack)) in enumerate(PROFILES.items()):
        tasks = NARRATIVES[direction]
        for index in range(2):
            required = list(stack) if index == 0 else stack[2:]+stack[:1]
            critical = required[:2]
            vid = f'v{len(vacancies)+1:03}'
            text = (f'Вакансия: {role}\nСинтетический проект {vid}\n\nЗадачи\n'
                + '\n'.join(tasks) + '\n\nТребования\n'
                + '\n'.join('Практический опыт: '+s+'.' for s in required)
                + '\nКритические требования: '+', '.join(critical)
                + '\nОпыт работы: от 2 лет\n\nУсловия\nПолная занятость, согласование приоритетов с командой.\n'
                'Синтетический документ для диагностических испытаний.')
            item = {'id':vid,'direction':direction,'title':role,'skills':required,
                    'critical_skills':critical,'text':text,'file':f'vacancies/{vid}.pdf'}
            write_structured_pdf(root/item['file'],text)
            vacancies.append(item)
        for index in range(40):
            # A fixed size distribution including weak and incomplete profiles.
            size = 0 if index % 20 == 0 else rng.randint(1,8)
            latent = set(rng.sample(stack,size))
            transition = index % 4 == 1
            if transition:
                foreign = sorted(stacks[(profile_index+1)%len(stacks)]-set(stack))
                if foreign:
                    latent.add(rng.choice(foreign))
            visible = sorted(latent)
            omissions = 1 if len(visible)>=3 and index%3 == 0 else 0
            for _ in range(omissions):
                visible.pop(rng.randrange(len(visible)))
            months = rng.choice([0,6,12,18,24,30,36,42,48,60,72,84,96,120])
            unknown = index%20 == 19
            rid = f'r{len(resumes)+1:03}'
            experience_format = 'unknown' if unknown else ('none' if months==0 else ('periods' if index%3==2 else 'explicit'))
            if unknown:
                experience = 'Опыт работы\nПериоды не указаны.'
            elif months==0:
                experience = 'Опыт работы\nБез опыта. Практика в рамках учебного проекта.'
            else:
                total = ' - '+duration(months) if experience_format=='explicit' else ''
                experience = f'Опыт работы{total}\n{period(months)}\nУчебная организация {rid}\nДолжность: {role}'
            rendered = [rng.choice(VARIANTS.get(s,[s])) for s in visible]
            listed = rendered[:len(rendered)//2]
            inline = rendered[len(rendered)//2:]
            duties = [RENDERED_MENTIONS[(index+j)%len(RENDERED_MENTIONS)].format(skill=s)
                      for j,s in enumerate(inline)]
            # Mentioned technology belongs to another team's work, explicitly
            # not this candidate's experience. It is NOT a positive skill label.
            contextual = []
            if index%5 == 2:
                foreign = sorted(set.union(*stacks)-latent)
                skill = rng.choice(foreign)
                contextual = [skill]
                duties.append(f'Соседняя команда использовала {skill}; лично с этой технологией не работал.')
            text = (f'Резюме\nФИО: Синтетический Кандидат {rid}\nГород: Тестовый город\n'
                'Контактные сведения исключены.\n\nЖелаемая должность\n'
                f'Специализация: {role}\nПолная занятость\n\n{experience}\n'
                + tasks[index%2]+'\n'+'\n'.join(duties)+'\n'+ACHIEVEMENTS[index%4]
                + '\n\nОбразование\n2012 - 2016\nУчебный университет\nИнформационные системы\n\nКлючевые навыки\n'
                + ('; '.join(listed) if listed else 'Отдельным списком не указаны.')
                + '\n\nОбо мне\n'
                + ('Рассматриваю переход в смежную область, готов обсуждать содержание задач.' if transition else
                   'Готов обсуждать содержание задач, ограничения и порядок проверки результата.')
                + '\nСведения вымышлены. Документ создан для диагностических испытаний.')
            item = {'id':rid,'direction':direction,'title':role,'latent_skills':sorted(latent),
                    'text_skills':visible,'context_only_skills':contextual,
                    'experience_years':None if unknown else round(months/12,2),
                    'experience_format':experience_format,'transition_profile':transition,
                    'text':text,'file':f'resumes/{rid}.pdf'}
            write_structured_pdf(root/item['file'],text)
            resumes.append(item)
    pairs = []
    for vacancy in vacancies:
        required,critical = set(vacancy['skills']),set(vacancy['critical_skills'])
        for resume in resumes:
            common = required & set(resume['latent_skills'])
            value = sum(2 if s in critical else 1 for s in common)/(len(required)+len(critical))
            pairs.append({'vacancy_id':vacancy['id'],'resume_id':resume['id'],'relevance':value})
    write_controls(root)
    data = {'version':VERSION,'style':'it','seed':SEED,'synthetic':True,
        'scoring_input_contract':'pdf_upload',
        'label_definition':'weighted latent skill coverage; critical=2; ordinary=1; same rule as pmi-hh-structured-1',
        'protocol':{'fixed_before_measurement':True,'selection':'one seed, every generated document and every pair',
            'profiles':'five overlapping IT specialties, forty resumes each, two vacancies each',
            'size':'index%20==0: zero skills; otherwise uniform 1..8',
            'transition':'index%4==1: add one skill from the next specialty if not already in this role stack',
            'omission':'one positive ability missing from text when size>=3 and index%3==0',
            'context_only':'index%5==2: one technology used by another team, explicitly no personal experience',
            'surface_forms':'fixed authored variants, selected with the registered seed',
            'experience':'fixed closed periods, optional explicit total; ten unspecified values',
            'score':'production formula, weights, model and dictionary unchanged',
            'thresholds':'same five numerical PMI limits; failure is an allowed recorded outcome',
            'layout_status':'authored HH-style sections; not an official HH export',
            'external_validity':'diagnostic stress test; not a representative real corpus or the presentation experiment'},
        'vacancies':vacancies,'resumes':resumes,'pairs':pairs}
    (root/'dataset.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return data
