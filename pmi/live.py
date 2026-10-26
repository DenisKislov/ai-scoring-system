"""Real A-1…A-17 service checks in an owned, isolated Compose project.

Never stops an existing user stack. No `down -v` on arbitrary projects. A newly
created test project and its synthetic data are removed at the end unless kept.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time
import uuid
import shutil
import tempfile
import httpx
from .dataset import verify


def run_live(dataset: Path, output: Path, keep=False):
    output.mkdir(parents=True,exist_ok=True)
    project = 'ai-scoring-pmi-' + uuid.uuid4().hex[:8]
    env = {**os.environ, 'API_PORT':'18000','FRONTEND_PORT':'13000',
           'MONGO_DB':'pmi_acceptance','API_CORS_ORIGINS':'http://localhost:13000',
           'DOCKER_PLATFORM':'linux/amd64'}
    # Prevent a user's .env MONGO_URI from attaching this test to their database.
    env['MONGO_URI'] = 'mongodb://mongo:27017'
    scratch = Path(tempfile.mkdtemp(prefix='pmi-compose-'))
    shutil.copytree('config',scratch/'config')
    override = scratch/'compose.override.json'
    override.write_text(json.dumps({'services': {
        name:{'volumes':[str(scratch/'config')+':/app/config:ro']} for name in ['backend','scorer']}}))
    compose = ['docker','compose','-f',str(Path('docker-compose.yml').resolve()),
               '-f',str(override),'--project-name',project]
    report = {'status':'not_run','project':project,'started_at':datetime.now(timezone.utc).isoformat(),
              'host':{'os':platform.platform(),'machine':platform.machine()},
              'cases':{},'manual_browser_check':'pending','kept':keep}
    log_path = output/'docker.log'
    log = log_path.open('w')
    started_stack = False

    def docker(*args, timeout=600):
        log.write('COMMAND '+ ' '.join(args)+'\n');log.flush()
        return subprocess.run(compose+list(args),env=env,stdout=log,stderr=log,timeout=timeout,check=True)

    def evidence(case, **details):
        report['cases'][case] = {'passed':True, **details}
        (output/'live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(f'{case}: пройдено',flush=True)

    def wait_health(client, timeout=180):
        start = time.perf_counter()
        while time.perf_counter()-start < timeout:
            try:
                if client.get('/health').status_code == 200:
                    return time.perf_counter()-start
            except httpx.HTTPError:
                pass
            time.sleep(.5)
        raise AssertionError('Health did not recover within timeout')

    def good(response, code=200):
        assert response.status_code == code, f'{response.request.url.path}: HTTP {response.status_code}: {response.text[:200]}'
        return response.json()

    try:
        if not verify(dataset)['ok']:
            raise AssertionError('Frozen dataset/config changed')
        info = subprocess.run(['docker','info','--format','{{json .}}'],capture_output=True,text=True,timeout=15)
        if info.returncode:
            report['reason']='Docker daemon unavailable'
            return report
        details=json.loads(info.stdout)
        report['docker']={k:details.get(k) for k in ['ServerVersion','Architecture','NCPU','MemTotal','OperatingSystem']}
        docker('build')
        started_stack = True
        docker('up','-d','--wait',timeout=240)
        data=json.loads((dataset/'dataset.json').read_text())
        with httpx.Client(base_url='http://localhost:18000',timeout=120) as client:
            wait_health(client)
            instance=good(client.get('/status'))['instance_id']
            server_config=good(client.get('/config'))
            frozen=json.loads((dataset/'manifest.json').read_text())['algorithm']
            # Dependency versions can differ by wheel/platform; the source hashes
            # and all declared algorithm parameters must agree across workers.
            assert server_config['file_hashes'] == frozen['file_hashes']
            source_hashes={item['id']:hashlib.sha256((dataset/item['file']).read_bytes()).hexdigest()
                           for item in data['vacancies']+data['resumes']}
            vids, rids = [], []
            start_total=time.perf_counter()
            for index,item in enumerate(data['vacancies']):
                if index in [0,2]:
                    doc=good(client.post('/vacancies',json={'title':item['title'],'description':item['text'],
                             'critical_skills':item['critical_skills']}),201)
                    vids.append(doc['_id'])
                else:
                    payload=(dataset/item['file']).read_bytes()
                    doc=good(client.post('/upload_vacancy',files={'file':(Path(item['file']).name,payload,'application/pdf')},
                                         data={'critical_skills':json.dumps(item['critical_skills'])}),201)
                    vids.append(doc['vacancy_id'])
                    original=client.get('/files/vacancies/'+vids[-1])
                    assert hashlib.sha256(original.content).hexdigest()==source_hashes[item['id']]
            start=time.perf_counter()
            for group in [data['resumes'][:100], data['resumes'][100:]]:
                files=[('files',(Path(r['file']).name,(dataset/r['file']).read_bytes(),'application/pdf')) for r in group]
                uploaded=good(client.post('/upload_resumes',files=files),201)
                assert uploaded['count']==100 and not uploaded['errors']
                rids.extend(r['resume_id'] for r in uploaded['results'])
                for source, result in zip(group,uploaded['results']):
                    assert result['original_sha256']==source_hashes[source['id']]
                    original=client.get('/files/resumes/'+result['resume_id'])
                    assert hashlib.sha256(original.content).hexdigest()==source_hashes[source['id']]
                if len(rids)==100:
                    batch100=time.perf_counter()-start
            assert len(set(vids))==10 and len(set(rids))==200
            assert good(client.get('/stats'))=={'vacancies':10,'resumes':200}
            evidence('A-1',vacancies=10,resumes=200,hashes_verified=208)
            alias=good(client.post('/upload_resume',files={'file':('aliases.pdf',(dataset/'controls/aliases.pdf').read_bytes())}),201)
            assert set(alias['skills'])=={'PostgreSQL','JavaScript','Kubernetes'}
            good(client.delete('/resumes/'+alias['resume_id']))
            evidence('A-2')
            first=good(client.post('/score',json={'vacancy_id':vids[0]}))
            second=good(client.post('/score',json={'vacancy_id':vids[0]}))
            assert first==second
            evidence('A-3',fingerprint=server_config['fingerprint'])
            rows=good(client.get('/results/'+vids[0]))['results']
            assert len(rows)==200 and len({r['_id'] for r in rows})==200
            assert all(0<=r['score']<=100 for r in rows)
            assert [(r['score'],r.get('experience_years') or 0) for r in rows]==sorted([(r['score'],r.get('experience_years') or 0) for r in rows],reverse=True)
            single=good(client.post('/score',json={'vacancy_id':vids[0],'resume_ids':[rids[0]]}))['results'][0]
            target=next(r for r in rows if r['resume_id']==rids[0])
            assert single['score']==target['score']
            evidence('A-4',unique_results=200)
            assert all('keyword_contribution' in r and 'missing_critical' in r and 'updated_at' in r for r in rows)
            assert good(client.get('/resumes/'+rids[0]))['_raw_text']
            evidence('A-5',scope='API explanation and source; browser appearance checked separately')
            decisions=[]
            for decision in ['yes','no']:
                decisions.append(good(client.post('/feedback',json={'vacancy_id':vids[0],'resume_id':rids[0],'decision':decision})))
            feedback=good(client.get('/feedback',params={'vacancy_id':vids[0],'resume_id':rids[0]}))
            assert feedback['decision']=='no' and [e['decision'] for e in feedback['history']]==['yes','no']
            evidence('A-6',history_events=2)
            assert good(client.get('/openapi.json'))['paths']['/score']
            assert client.post('/score',json={}).status_code==422
            assert client.get('/results/missing').status_code==404
            evidence('A-7')
            small=good(client.post('/score',json={'vacancy_id':vids[0],'resume_ids':rids[:10]}))
            large=good(client.post('/score',json={'vacancy_id':vids[0],'resume_ids':rids}))
            a=next(r for r in small['results'] if r['resume_id']==rids[0])
            b=next(r for r in large['results'] if r['resume_id']==rids[0])
            assert a['score']==b['score']
            evidence('A-12',score_pool10=a['score'],score_pool200=b['score'])
            durations=[]
            for vid in vids:
                before=time.perf_counter();scored=good(client.post('/score',json={'vacancy_id':vid}));durations.append(time.perf_counter()-before)
                assert scored['count']==200
            total=time.perf_counter()-start_total
            before=time.perf_counter()
            one=good(client.post('/upload_resume',files={'file':('one.pdf',(dataset/data['resumes'][0]['file']).read_bytes())}),201)
            one_seconds=time.perf_counter()-before
            good(client.delete('/resumes/'+one['resume_id']))
            assert total<=3600 and batch100<=1800 and one_seconds<=120 and max(durations)<=10
            evidence('A-16',total_seconds=total,batch100_seconds=batch100,single_seconds=one_seconds,ranking200_max_seconds=max(durations))
            for control in ['empty.txt','broken.pdf','unsupported.doc','no_text.pdf']:
                for endpoint in ['/upload_resume','/upload_vacancy']:
                    response=client.post(endpoint,files={'file':(control,(dataset/'controls'/control).read_bytes())})
                    assert response.status_code==400 and response.json()['detail']
            for endpoint in ['/vacancies','/candidates']:
                assert client.post(endpoint,json={'title':' '}).status_code==422
            assert good(client.get('/status'))['instance_id']==instance
            evidence('A-13')
            control_vac=good(client.post('/vacancies',json={
                'title':'Контроль критических навыков', 'description':'Python PostgreSQL Docker Git',
                'critical_skills':['Python','PostgreSQL']}),201)['_id']
            control_resumes=[]
            for name in ['critical_all','critical_none','personal_a','personal_b']:
                c=good(client.post('/upload_resume',files={'file':(name+'.pdf',(dataset/'controls'/f'{name}.pdf').read_bytes())}),201)
                control_resumes.append(c['resume_id'])
            control=good(client.post('/score',json={'vacancy_id':control_vac,'resume_ids':control_resumes}))['results']
            control_byid={r['resume_id']:r for r in control}
            a,b=(control_byid[rid] for rid in control_resumes[:2])
            assert len(a['matched_skills'])==len(b['matched_skills'])==2 and a['score']>b['score']
            evidence('A-11',critical_all_score=a['score'],critical_none_score=b['score'])
            a,b=(control_byid[rid] for rid in control_resumes[2:])
            assert a['score']==b['score'] and a['cosine_sim']==b['cosine_sim']
            evidence('A-17',equal_score=a['score'])
            good(client.delete('/vacancies/'+control_vac))
            for rid in control_resumes:
                good(client.delete('/resumes/'+rid))
            before=list(rows)
            # A-14 stops only the new test project's database.
            docker('stop','mongo',timeout=30)
            assert client.get('/stats').status_code==503
            assert client.post('/score',json={'vacancy_id':vids[0]}).status_code==503
            assert good(client.get('/status'))['instance_id']==instance
            docker('start','mongo',timeout=30);wait_health(client)
            assert good(client.get('/stats'))['resumes']==200
            assert good(client.get('/status'))['instance_id']==instance
            evidence('A-14',same_api_instance=True)
            # All A-1…A-17 checks before the required A-15 restart used one API process.
            logs=good(client.get('/logs',params={'lines':5000}))['logs']
            text='\n'.join(e['message'] for e in logs)
            assert all(name in text for name in ['upload_completed','scoring_started','scoring_completed','extraction_error','database_error'])
            good(client.delete('/vacancies/'+vids[2]))
            assert client.get('/results/'+vids[2]).status_code==404
            good(client.delete('/resumes/'+rids[-1]))
            assert all(r['resume_id']!=rids[-1] for r in good(client.get('/results/'+vids[0]))['results'])
            evidence('A-8',events_verified=True,cascades_verified=True)
            persisted=good(client.get('/stats'))
            recovery_start=time.perf_counter()
            docker('stop',timeout=60)
            docker('start',timeout=60)
            recovered=wait_health(client)
            total_recovery=time.perf_counter()-recovery_start
            assert total_recovery<=1800 and good(client.get('/stats'))==persisted
            assert good(client.get('/feedback',params={'vacancy_id':vids[0],'resume_id':rids[0]}))['decision']=='no'
            original=client.get('/files/resumes/'+rids[0]);assert hashlib.sha256(original.content).hexdigest()==source_hashes[data['resumes'][0]['id']]
            evidence('A-15',recovery_seconds=total_recovery,stats=persisted,feedback_and_original_intact=True)
            dictionary_path=scratch/'config/skills.json'
            original_dictionary=dictionary_path.read_bytes()
            extended=json.loads(original_dictionary)
            for index in range(15):
                extended['directions'][f'Дополнительное направление {index+1}']={f'Лазерная метрология {index+1}':[f'квантметр{index+1}']}
            try:
                dictionary_path.write_text(json.dumps(extended,ensure_ascii=False))
                expected_hash=hashlib.sha256(dictionary_path.read_bytes()).hexdigest()
                # Docker Desktop bind mounts can publish a host write after the
                # first HTTP request. Wait for the actual worker to see it;
                # never restart the API or scoring process to refresh skills.
                deadline=time.perf_counter()+5
                while True:
                    observed=good(client.get('/config'))['file_hashes']['config/skills.json']
                    if observed==expected_hash:
                        break
                    if time.perf_counter()>=deadline:
                        raise AssertionError('Mounted dictionary was not synchronized in 5 seconds')
                    time.sleep(.1)
                while True:
                    added=good(client.post('/upload_resume',files={'file':('new.txt','Навыки: квантметр15.','text/plain')}),201)
                    observed_skill='Лазерная метрология 15' in added['skills']
                    good(client.delete('/resumes/'+added['resume_id']))
                    if observed_skill:
                        break
                    if time.perf_counter()>=deadline:
                        raise AssertionError('New direction was not extracted after mount synchronization')
                    time.sleep(.1)
            finally:
                dictionary_path.write_bytes(original_dictionary)
            evidence('A-20',directions=20,code_changes=0,restart_required=False)
            browser=httpx.get('http://localhost:13000',timeout=10)
            assert browser.status_code==200 and '<div id="root">' in browser.text
            evidence('A-19',scope='four amd64 Linux containers and HTTP UI delivery; customer independent/browser verification pending')
        report['status']='passed'
    except (Exception,KeyboardInterrupt) as exc:
        report['status']='failed'
        report['reason']=f'{type(exc).__name__}: {str(exc)[:500]}'
    finally:
        if started_stack:
            try:
                docker('logs','--no-color',timeout=30)
                if not keep:
                    docker('down','--volumes',timeout=60)
            except Exception as exc:
                report['cleanup_error']=type(exc).__name__
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        log.close()
        (output/'live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report
