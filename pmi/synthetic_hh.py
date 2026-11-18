"""Versioned synthetic corpus with HH-style sections, never real people's data.

This is an authored layout following public HH guidance, not an actual HH export.
No production extractor, dictionary, scorer or model is imported by the generator.
The seed and noise rules are fixed before the first quality measurement.
"""
from __future__ import annotations

import json
from pathlib import Path
import random
import textwrap

import fitz

from .dataset import PROFILES, write_controls

VERSION = 'pmi-hh-structured-1'
SEED = 20261118
ALIASES = {
    'PostgreSQL':'Postgres', 'pytest':'PyTest', 'Git':'git',
    '1С: Бухгалтерия':'1С Бухгалтерия', 'Налоговый учёт':'налоговый учет',
    'Банк-клиент':'банк-клиент', 'Битрикс24':'Битрикс 24',
    'Яндекс Директ':'Яндекс.Директ', 'Яндекс Метрика':'Яндекс.Метрика',
    'A/B-тестирование':'A/B тестирование', 'КОМПАС':'Компас',
    'Расчёт прочности':'расчет прочности',
}
CONTEXT = {
    'Разработка ПО':(
        'Разработка внутренних сервисов обработки заявок и интеграций между системами.',
        'Подготовка изменений в продукте, проверка поведения и сопровождение выпуска.',
        'Прикладная информатика',
        'Снизил число ручных операций при обработке заявок; результат принят командой.'),
    'Бухгалтерия':(
        'Ведение учётных участков торговой организации и сверка первичных документов.',
        'Подготовка материалов к закрытию периода и проверка расхождений с контрагентами.',
        'Экономика и учёт',
        'Сократил срок сверки документов за счёт единого порядка проверки расхождений.'),
    'Продажи':(
        'Развитие клиентского портфеля поставщика оборудования для организаций.',
        'Обработка обращений, подготовка предложений и сопровождение исполнения заказов.',
        'Коммерция',
        'Вернул часть неактивных клиентов; повторные заказы включены в квартальный план.'),
    'Маркетинг':(
        'Привлечение обращений для каталога услуг и оценка результата рекламных размещений.',
        'Подготовка материалов, сравнение вариантов подачи и контроль стоимости обращения.',
        'Реклама и связи с общественностью',
        'Снизил стоимость обращения после пересмотра структуры размещений и материалов.'),
    'Проектирование':(
        'Разработка узлов промышленного оборудования и сопровождение выпуска изделий.',
        'Подготовка документации, согласование изменений с производством и проверка размеров.',
        'Машиностроение',
        'Уменьшил число возвратов документации после введения проверки перед передачей.'),
}
# Sources describe task families. Texts below are our paraphrases and composites,
# not copies of individual vacancies. Access to SuperJob was blocked by CAPTCHA.
SOURCES = {
    'resume_structure':{'url':'https://hh.ru/article/kak-sostavit-rezyume',
        'scope':'public guidance on sections; exact HH PDF export compatibility unverified'},
    'Разработка ПО':{'url':'https://hh.ru/vacancies/python-django-developer/ot_pryamih_rabotodateley?page=0',
        'basis':'backend services, Python/Django, databases and testing'},
    'Бухгалтерия':{'url':'https://hh.ru/vacancies/bukhgalter_po_msfo/ot_pryamih_rabotodateley',
        'basis':'accounting, reporting, reconciliation, РСБУ/МСФО'},
    'Продажи':{'url':'https://hh.ru/vacancies/menedzher-po-rabote-s-klientami-holodnye-zvonki',
        'basis':'B2B customer acquisition and outbound sales'},
    'Маркетинг':{'url':'https://hh.ru/vacancies/internet-marketolog-seo',
        'basis':'lead generation, SEO and advertising campaigns'},
    'Проектирование':{'url':'https://hh.ru/vacancies/inzhener-konstruktor-2-kategorii/ot_pryamih_rabotodateley',
        'basis':'engineering documentation, product design and ЕСКД'},
}
MONTHS = ['Январь','Февраль','Март','Апрель','Май','Июнь',
          'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь']


def duration(months):
    years, rest = divmod(months,12)
    suffix = 'год' if years % 10 == 1 and years % 100 != 11 else (
        'года' if years % 10 in [2,3,4] and years % 100 not in [12,13,14] else 'лет')
    if not years:
        return f'{rest} месяцев'
    return f'{years} {suffix}' + (f' {rest} месяцев' if rest else '')


def period(months):
    # Closed dates; there is no moving "present" boundary or dependence on now.
    end = 2025*12+9  # October 2025
    start = end-months
    sy,sm = divmod(start,12)
    ey,em = divmod(end,12)
    return f'{MONTHS[sm]} {sy} - {MONTHS[em]} {ey}'


def write_structured_pdf(path, text):
    """Deterministic, readable one-column PDF with an embedded Cyrillic font."""
    font = fitz.Font('cjk')
    headings = ('Желаемая должность','Опыт работы','Ключевые навыки',
                'Образование','Обо мне','Требования','Задачи','Условия')
    with fitz.open() as doc:
        page, y = None, 0
        for line in text.splitlines():
            for chunk in textwrap.wrap(line,88,break_long_words=False,break_on_hyphens=False) or ['']:
                if page is None or y > 777:
                    page = doc.new_page(width=595,height=842)
                    page.insert_font(fontname='pmi',fontbuffer=font.buffer)
                    y = 48
                heading = chunk.startswith(headings)
                size = 12 if heading else 10
                if font.text_length(chunk,fontsize=size) > 507:
                    raise ValueError('PDF line exceeds content area')
                if heading:
                    page.draw_line((44,y+4),(551,y+4),color=(.75,.78,.82),width=.4)
                page.insert_text((44,y),chunk,fontname='pmi',fontsize=size,
                                 color=(.13,.23,.36) if heading else (.12,.12,.12))
                y += 20 if heading else (15 if chunk else 9)
        for index,page in enumerate(doc):
            page.insert_text((44,819),f'Synthetic / {index+1}',fontname='pmi',fontsize=8,color=(.4,.4,.4))
        doc.subset_fonts()
        doc.set_metadata({'title':'Synthetic structured acceptance document',
                          'producer':VERSION})
        doc.save(path,garbage=4,deflate=True,no_new_id=True)


def generate(root: Path):
    rng = random.Random(SEED)
    root.mkdir(parents=True,exist_ok=True)
    for kind in ['vacancies','resumes','controls']:
        (root/kind).mkdir(exist_ok=True)
    vacancies,resumes = [],[]
    for direction,(role,stack) in PROFILES.items():
        task,work,education,achievement = CONTEXT[direction]
        for index in range(2):
            required = list(stack) if index == 0 else stack[2:]+stack[:1]
            critical = required[:2]
            vid = f'v{len(vacancies)+1:03}'
            text = (f'Вакансия: {role}\nОрганизация: Учебный проект {vid}\n'
                    f'Направление: {direction}\n\nЗадачи\n{task}\n{work}\n\nТребования\n'
                    + '\n'.join('- '+s for s in required)
                    + '\nКритические требования: '+', '.join(critical)
                    + '\nОпыт работы: от 2 лет\n\nУсловия\nПолная занятость, пятидневная неделя.\n'
                    'Регулярная обратная связь по результатам работы.\n'
                    'Синтетическая вакансия. Текст составлен для испытаний.')
            item = {'id':vid,'direction':direction,'title':role,'skills':required,
                    'critical_skills':critical,'text':text,'file':f'vacancies/{vid}.pdf',
                    'public_task_source':SOURCES[direction]['url']}
            write_structured_pdf(root/item['file'],text)
            vacancies.append(item)
        for index in range(40):
            # Uniform ability sizes, not a hand-picked list of high scorers.
            latent = sorted(rng.sample(stack,rng.randint(1,8)))
            visible = list(latent)
            if len(visible) >= 4 and index % 5 == 0:
                visible.pop(rng.randrange(len(visible)))
            rendered = [ALIASES.get(s,s) if (index+j)%3 == 0 else s for j,s in enumerate(visible)]
            months = rng.choice([0,6,12,18,24,30,36,42,48,60,72,84,96,120,144])
            unknown = index % 20 == 19
            rid = f'r{len(resumes)+1:03}'
            mode = index % 3
            if unknown:
                experience = 'Опыт работы\nСведения о периодах не указаны.'
            elif months == 0:
                experience = 'Опыт работы\nБез опыта. Учебные задания по выбранной специальности.'
            else:
                total = '' if mode == 2 else ' - '+duration(months)
                experience = f'Опыт работы{total}\n{period(months)}\nУчебная организация {rid}\nДолжность: {role}'
            listed = rendered if mode != 1 else rendered[::2]
            in_duties = [] if mode != 1 else rendered[1::2]
            skills = ('; '.join(listed) if mode != 2 else '\n'.join('- '+s for s in listed))
            duties = '\n'.join(f'Выполнял профильные задачи, применяя {s}.' for s in in_duties)
            experience += f'\n{work}\n{duties}\n{achievement}'
            text = (f'Резюме\nФИО: Синтетический Кандидат {rid}\n'
                    f'Город: Тестовый город {index%4+1}\nКонтакты: не используются в испытаниях.\n\n'
                    f'Желаемая должность\nСпециализация: {role}\n'
                    'Занятость: полная\nГрафик: полный день\n\n'
                    f'{experience}\n\nОбразование\n2012 - 2016\nУчебный университет\n{education}\n\n'
                    f'Ключевые навыки\n{skills}\n\nОбо мне\n{task}\n'
                    'Готов обсуждать содержание задач и получать обратную связь.\n'
                    'Все сведения вымышлены. Документ создан для испытаний.')
            item = {'id':rid,'direction':direction,'title':role,'latent_skills':latent,
                    'text_skills':visible,'experience_years':None if unknown else round(months/12,2),
                    'experience_format':'unknown' if unknown else ('none' if months == 0 else ['explicit','explicit_with_inline_skills','closed_periods'][mode]),
                    'layout_variant':mode,'text':text,'file':f'resumes/{rid}.pdf'}
            write_structured_pdf(root/item['file'],text)
            resumes.append(item)
    pairs = []
    for vacancy in vacancies:
        required,critical = set(vacancy['skills']),set(vacancy['critical_skills'])
        for resume in resumes:
            relevant = required & set(resume['latent_skills'])
            value = sum(2 if skill in critical else 1 for skill in relevant)/(len(required)+len(critical))
            pairs.append({'vacancy_id':vacancy['id'],'resume_id':resume['id'],'relevance':value})
    write_controls(root)
    dataset = {'version':VERSION,'style':'hh','seed':SEED,'synthetic':True,
        'scoring_input_contract':'pdf_upload',
        'label_definition':'weighted latent skill coverage; critical=2; ordinary=1; authored before scoring',
        'protocol':{'fixed_seed':SEED,'resumes_per_direction':40,'vacancies_per_direction':2,
                    'ability_size':'uniform integer 1..8',
                    'omissions':'one ability omitted when index%5==0 and size>=4',
                    'aliases':'fixed manual map; applied when (index+skill_index)%3==0',
                    'inline_skill_mentions':'every second visible skill for layout variant 1',
                    'experience':'closed dates ending October 2025; unknown when index%20==19',
                    'selection':'all generated documents and all pairs; no result-based selection',
                    'layout_status':'authored HH-style sections; not exported by HH; formal template conformity pending',
                    'label_status':'generator-defined synthetic abilities; no independent expert judgement',
                    'acceptance_limits':{'ndcg_at_10':.9,'precision_at_5':.9,'precision_at_10':.9,'recall_at_10':.15,'spearman':.8}},
        'sources':SOURCES,'vacancies':vacancies,'resumes':resumes,'pairs':pairs}
    (root/'dataset.json').write_text(json.dumps(dataset,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return dataset
