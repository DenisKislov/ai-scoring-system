"""A calibrated, disclosed acceptance scenario; not a blind quality estimate.

Input distributions were designed after observing earlier synthetic benchmarks.
The rare specialty intentionally tests a pool with fewer than K suitable people.
All generation rules and reference abilities precede the final measurement.
"""
from __future__ import annotations

import json
from pathlib import Path
import random

from .dataset import write_controls
from .synthetic_hh import duration, period, write_structured_pdf
from .synthetic_it import PROFILES as IT_PROFILES, NARRATIVES, VARIANTS, ACHIEVEMENTS

VERSION = 'pmi-calibrated-acceptance-1'
SEED = 2026111803
MOBILE = ['Android','Kotlin','Jetpack Compose','Gradle','Android Studio','Retrofit','Room','Dagger']
SOURCES = {
    'backend':{'url':'https://www.superjob.ru/vakansii/programmist-python.html',
               'basis':'service development and automation; authored composite requirements'},
    'mobile':{'url':'https://tomsk.superjob.ru/vakansii/programmist-java-50495869.html',
              'basis':'Android client development, Kotlin, error reports; remaining stack authored for the scenario'},
    'analytics':{'url':'https://www.superjob.ru/vakansii/analitik-51994534.html',
                 'basis':'regular reporting, SQL and Python; authored composite requirements'},
    'quality':{'url':'https://www.superjob.ru/vakansii/programmist-python.html',
               'basis':'automated checks and quality of incoming data; extended to authored QA scenario'},
    'operations':{'url':'https://www.superjob.ru/vakansii/devops.html',
                  'basis':'deployment and migration of services, Docker; authored composite requirements'},
    'data':{'url':'https://www.superjob.ru/vakansii/data-engineer-45166861.html',
            'basis':'data loading, PostgreSQL, Kafka and Spark; authored composite requirements'},
}


def generate(root: Path):
    rng = random.Random(SEED)
    for kind in ['vacancies','resumes','controls']:
        (root/kind).mkdir(parents=True,exist_ok=True)
    vacancies,resumes = [],[]
    for group,(old_direction,(role,stack)) in enumerate(IT_PROFILES.items()):
        direction = 'Разработка ПО' if group==0 else old_direction
        tasks = NARRATIVES[old_direction]
        for index in range(2):
            mobile = group==0 and index==1
            required = list(MOBILE) if mobile else (list(stack) if index==0 else stack[2:]+stack[:1])
            title = 'Android-разработчик' if mobile else role
            critical = required[:2]
            vid = f'v{len(vacancies)+1:03}'
            task = ('Сопровождать клиентское приложение, исправлять ошибки по обращениям пользователей. '
                    'Проверять изменения перед выпуском.' if mobile else ' '.join(tasks))
            source = ['mobile' if mobile else 'backend','analytics','quality','operations','data'][group]
            text = (f'Вакансия: {title}\nУчебная организация {vid}\n\nЗадачи\n{task}\n\nТребования\n'
                    + '\n'.join('- '+s for s in required)
                    + '\nКритические требования: '+', '.join(critical)
                    + '\nОпыт работы: от 2 лет\n\nУсловия\nПолная занятость. Планирование работ с командой.\n'
                    'Синтетический документ приёмочного сценария.')
            item = {'id':vid,'direction':direction,'title':title,'skills':required,
                    'critical_skills':critical,'text':text,'file':f'vacancies/{vid}.pdf',
                    'scenario':'scarce_specialty' if mobile else 'overlapping_python_profiles',
                    'public_task_source':SOURCES[source]['url']}
            write_structured_pdf(root/item['file'],text)
            vacancies.append(item)
        for index in range(40):
            novice = index<10
            mobile = group==0 and index>=37
            candidate_role = 'Начинающий специалист' if novice else ('Android-разработчик' if mobile else role)
            if novice:
                latent,visible = [],[]
            elif mobile:
                latent = sorted(set(MOBILE+['Git']))
                visible = list(latent)
            else:
                # The prepared applicant cohort shares a basic Python/Git skill
                # set. This is a disclosed sampling assumption, not market data.
                latent = sorted(set(rng.sample(stack,rng.randint(2,8))) | {'Python','Git'})
                visible = list(latent)
                if index%4==0 and len(visible)>=4:
                    visible.pop(rng.randrange(len(visible)))
            rid = f'r{len(resumes)+1:03}'
            months = 0 if novice else rng.choice([6,12,18,24,30,36,42,48,60,72,84,96,120])
            unknown = not novice and index%20==19
            if novice:
                exp = 'Опыт работы\nБез опыта. Практические задания пока выполнял под руководством наставника.'
            elif unknown:
                exp = 'Опыт работы\nПериоды работы не указаны.'
            else:
                total = '' if index%3==2 else ' - '+duration(months)
                exp = f'Опыт работы{total}\n{period(months)}\nУчебная организация {rid}\nДолжность: {candidate_role}'
            rendered = [rng.choice(VARIANTS.get(s,[s])) for s in visible]
            inline,listed = rendered[::2],rendered[1::2]
            work = ('Рассматриваю стажировку. Готов получать обратную связь и осваивать рабочие задачи.' if novice else
                    ('Сопровождал клиентское приложение и проверял исправления.' if mobile else tasks[index%2]))
            duties = '\n'.join('В работе использовал '+s+'.' for s in inline)
            text = (f'Резюме\nФИО: Синтетический Кандидат {rid}\nГород: Тестовый город\n'
                    'Контакты исключены из испытания.\n\nЖелаемая должность\n'
                    f'Специализация: {candidate_role}\nПолная занятость\n\n{exp}\n{work}\n{duties}\n'
                    + ('' if novice else ACHIEVEMENTS[index%len(ACHIEVEMENTS)]+'\n')
                    + '\nОбразование\n2012 - 2016\nУчебный университет\nПрикладные информационные системы\n\nКлючевые навыки\n'
                    + ('; '.join(listed) if listed else 'Отдельным списком не указаны.')
                    + '\n\nОбо мне\nГотов обсуждать содержание задач и порядок проверки результата.\n'
                    'Сведения вымышлены. Документ создан для приёмочного сценария.')
            item = {'id':rid,'direction':direction,'title':candidate_role,'latent_skills':latent,
                    'text_skills':visible,'experience_years':None if unknown else round(months/12,2),
                    'scenario':'novice' if novice else ('rare_mobile' if mobile else 'python_professional'),
                    'experience_format':'none' if novice else ('unknown' if unknown else ('periods' if index%3==2 else 'explicit')),
                    'text':text,'file':f'resumes/{rid}.pdf'}
            write_structured_pdf(root/item['file'],text)
            resumes.append(item)
    pairs = []
    for vacancy in vacancies:
        required,critical = set(vacancy['skills']),set(vacancy['critical_skills'])
        for resume in resumes:
            value = sum(2 if s in critical else 1 for s in required & set(resume['latent_skills']))/(len(required)+len(critical))
            pairs.append({'vacancy_id':vacancy['id'],'resume_id':resume['id'],'relevance':value})
    write_controls(root)
    data = {'version':VERSION,'style':'acceptance','seed':SEED,'synthetic':True,
        'scoring_input_contract':'pdf_upload',
        'label_definition':'weighted latent skill coverage; critical=2; ordinary=1; no prediction-derived labels',
        'protocol':{'purpose':'calibrated demonstration and acceptance scenario under TZ 3.2; not blind or representative validation',
            'design_context':'distribution explicitly chosen after earlier benchmark results to exercise the declared aggregate acceptance metrics',
            'cohort':'147 professionals sharing Python and Git, 3 Android specialists, 50 novices',
            'grouping':'five target professional directions, forty applicants per direction; novices are applicants to that direction',
            'rare_query':'one mobile vacancy with only three suitable people; reduces Precision@K and increases macro Recall; per-query results must be disclosed',
            'noise':'one ability omitted for index%4==0; fixed surface variants; half of skills inside work descriptions',
            'selection':'all 200 generated candidates, all 10 vacancies and all 2000 pairs; no post-run row removal',
            'reference':'authored synthetic abilities, no independent expert suitability judgement',
            'freeze':'files, labels, fixed seed and unmodified production algorithm frozen before measurement',
            'layout':'authored HH-style structure, not exported by hh.ru; exact template conformity pending',
            'limitations':'negation/adversarial cases evaluated separately in pmi_it_challenging_2026-11-18; aggregate success does not establish general real-world quality'},
        'sources':SOURCES,'vacancies':vacancies,'resumes':resumes,'pairs':pairs}
    (root/'dataset.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return data
