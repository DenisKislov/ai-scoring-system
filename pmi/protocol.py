"""Combine evidence without turning unexecuted manual checks into passes."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
from xml.etree import ElementTree as ET

REQUIREMENTS = {
    'A-1':'Ф-1', 'A-2':'Ф-2', 'A-3':'Ф-3', 'A-4':'Ф-4', 'A-5':'Ф-5, Ф-6',
    'A-6':'Ф-7', 'A-7':'Ф-6, Ф-8', 'A-8':'Ф-9', 'A-9':'К-1—К-6',
    'A-10':'К-7', 'A-11':'К-8', 'A-12':'К-9', 'A-13':'Н-1', 'A-14':'Н-2',
    'A-15':'Н-3', 'A-16':'Н-4', 'A-17':'Б-1', 'A-18':'Б-2',
    'A-19':'С-1, П-1', 'A-20':'С-3',
}


def protocol(out: Path) -> dict:
    def read(name):
        path=out/name
        return json.loads(path.read_text()) if path.exists() else {}
    quality, live, audit = read('quality.json'), read('live.json'), read('privacy_audit.json')
    unit_cases, unit_total, unit_failures = {}, 0, 0
    if (out/'unit.xml').exists():
        root=ET.parse(out/'unit.xml').getroot()
        for test in root.iter('testcase'):
            unit_total+=1
            failed=test.find('failure') is not None or test.find('error') is not None
            skipped=test.find('skipped') is not None
            unit_failures+=int(failed)
            match=re.match(r'test_a(\d\d)_',test.get('name',''))
            if match:
                case='A-'+str(int(match[1]))
                unit_cases.setdefault(case,[]).append(not failed and not skipped)
    manual = read('manual_evidence.json')
    required_manual = ['browser_a4_a5','swagger_a7','customer_a19','personal_data_review',
                       'documentation_complete','commission_acceptance']
    manual_complete = bool(manual.get('verified_by') and manual.get('date')) and all(manual.get('checks',{}).get(k) is True for k in required_manual)
    try:
        tag = subprocess.check_output(['git','describe','--exact-match','--tags','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
        clean = subprocess.run(['git','diff','--quiet','HEAD'],check=False).returncode==0
    except subprocess.SubprocessError:
        tag,clean=None,False
    rows=[]
    for index in range(1,21):
        case=f'A-{index}'
        automatic=bool(unit_cases.get(case)) and all(unit_cases[case])
        state='пройдено автоматически' if automatic else 'нет результата'
        scope='pytest; API/хранилище с имитацией MongoDB' if automatic else ''
        if case=='A-9':
            state='пройдено' if quality and all(c['passed'] for c in quality.get('criteria',{}).values()) else 'не пройдено / нет отчёта'
            scope='фиксированный PDF-набор; quality.json'
        if case=='A-10':
            state='пройдено' if quality.get('a10',{}).get('passed') else 'не пройдено / нет отчёта'
            scope='все нулевые и сильные пары; quality.json'
        if case in live.get('cases',{}):
            state='пройдено в Docker' if live['cases'][case]['passed'] else 'не пройдено'
            scope='настоящие API, MongoDB и отдельный сервис скоринга'
        if case in ['A-5','A-7']:
            scope+='; внешний вид/Swagger — по ручному листу'
        if case in ['A-14','A-15','A-16'] and case not in live.get('cases',{}):
            state='ожидает Docker-прогона'
            scope='имитация/локальное измерение не заменяют остановку контейнеров'
        if case=='A-18':
            state='требует проверки' if not audit.get('automated_passed') else 'автопоиск пройден; нужна экспертиза ПДн'
            scope=f'секреты: {audit.get("secret_findings","—")}; контакты-кандидаты: {audit.get("contact_candidates","—")}; история Git проверяется отдельно от игнорируемых PDF'
        if case=='A-19':
            state='техническая часть пройдена; ручная часть ожидается' if case in live.get('cases',{}) else 'ожидает проверки на чистом стенде'
            scope='представитель Заказчика; выбранные браузеры; без участия разработчика'
        rows.append({'case':case,'requirements':REQUIREMENTS[case],'status':state,'evidence':scope})
    accepted = (bool(quality.get('passed')) and live.get('status')=='passed' and unit_total>0 and unit_failures==0
                and bool(audit.get('automated_passed')) and manual_complete and bool(tag) and clean)
    result={'date':datetime.now(timezone.utc).isoformat(),'accepted':accepted,
            'release_tag':tag,'tracked_tree_clean':clean,'manual_evidence_complete':manual_complete,
            'unit':{'tests':unit_total,'failures':unit_failures},'cases':rows,
            'quality_passed':quality.get('passed',False),'live_status':live.get('status','not_run'),
            'manual_pending':([] if manual_complete else ['А-19: независимое развёртывание и браузеры','Б-2: экспертиза происхождения данных',
                              'Д-1: актуальный ТЗ v5, комплект документов, утверждённый тег',
                              'П-1: представитель Заказчика','Подписи комиссии и акт'])}
    out.mkdir(parents=True,exist_ok=True)
    (out/'protocol.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    lines=['# Протокол испытаний по ПМИ Т1-1', '',f'Сформирован: {result["date"]}.',
           '', ('**Статус: все технические критерии и внесённые комиссией свидетельства подтверждены.**' if accepted else '**Статус: технические проверки и доказательства приведены ниже; формальная приёмка комиссией не оформлена.**'),
           '', f'Python: {unit_total} тестов, ошибок {unit_failures}. Docker: {result["live_status"]}.',
           '', '| Пример | Требования | Результат | Доказательство и границы |', '|---|---|---|---|']
    lines += [f'| {r["case"]} | {r["requirements"]} | {r["status"]} | {r["evidence"]} |' for r in rows]
    lines += ['', '## Комплектность и ручные действия', '']
    lines += ['- '+item for item in result['manual_pending']]
    lines += ['', 'С-2: полный pytest и тесты фронтенда запускаются по README. Д-2: 200 синтетических резюме, по 40 на каждое из пяти направлений, 10 вакансий, 2000 размеченных пар.',
              'Локальные показатели текущего Mac не заменяют характеристики приёмочного стенда x86-64 Linux/Windows. Docker-образы настроены на linux/amd64; архитектура и ресурсы хоста записаны в live.json.',
              'ПМИ ссылается на ТЗ v5 от 12.10.2026; имеющийся исходный ТЗ содержит более ранний порог 0.80. Для качества здесь применены более строгие численные критерии самой ПМИ.',
              '', 'Файлы доказательств: quality.json/md, unit.xml, performance_local.json, live.json, privacy_audit.json. Подписей и результатов неисполненных ручных проверок этот протокол не подменяет.']
    (out/'protocol.md').write_text('\n'.join(lines)+'\n')
    return result
