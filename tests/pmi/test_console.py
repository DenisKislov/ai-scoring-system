"""CLI results stay in the terminal; failures retain a nonzero exit code."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from pmi import __main__ as cli
from pmi.live_quality import evaluate_api_outputs

PROJECT = Path(__file__).resolve().parents[2]


@pytest.fixture
def quality_result():
    return json.loads((PROJECT / 'reports/pmi_release_2026-11-18/quality_api.json').read_text())


@pytest.fixture
def console_workspace(tmp_path, monkeypatch):
    dataset = tmp_path / 'inputs'
    dataset.mkdir()
    (dataset / 'manifest.json').write_text('{}')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, 'DEFAULT_DATASET', dataset)
    monkeypatch.setattr(cli, 'restore_missing', lambda _: [])
    return tmp_path


def test_verify_creates_no_report_directory(console_workspace, monkeypatch, capsys):
    monkeypatch.setattr(cli, 'verify', lambda _: {'ok': True, 'errors': []})
    monkeypatch.setattr(sys, 'argv', ['pmi', 'verify'])
    assert cli.main() == 0
    assert 'Целостность: ПРОЙДЕНО' in capsys.readouterr().out
    assert {path.name for path in console_workspace.iterdir()} == {'inputs'}


@pytest.mark.parametrize('passed', [True, False])
def test_quality_prints_metrics_without_writing_files(console_workspace, monkeypatch, capsys, quality_result, passed):
    from pmi import quality
    quality_result['passed'] = passed
    quality_result['criteria']['recall_at_10']['passed'] = passed

    def evaluate(dataset, output):
        assert dataset == console_workspace / 'inputs'
        assert output is None
        return quality_result

    monkeypatch.setattr(quality, 'evaluate', evaluate)
    monkeypatch.setattr(sys, 'argv', ['pmi', 'quality'])
    assert cli.main() == (0 if passed else 1)
    output = capsys.readouterr().out
    assert 'NDCG@10' in output and '0.9401' in output
    assert 'Извлечение навыков' not in output and '0.9228' not in output
    assert {path.name for path in console_workspace.iterdir()} == {'inputs'}


def test_api_evaluation_returns_metrics_without_output_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = {'version': 'test', 'synthetic': True,
            'vacancies': [{'id': 'v', 'direction': 'test', 'skills': ['Python']}],
            'resumes': [{'id': 'r', 'text_skills': ['Python'], 'experience_years': 2}],
            'pairs': [{'vacancy_id': 'v', 'resume_id': 'r', 'relevance': 1}]}
    documents = {rid: {'skills': ['Python'], 'experience_years': 2} for rid in ['v', 'r']}
    report = evaluate_api_outputs(data, documents, {'v': [{'candidate_id': 'r', 'score': 100}]})
    assert report['metrics']['ndcg_at_10'] == 1
    assert report['skill_extraction_micro']['resumes']['f1'] == 1
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(('quality_passed', 'unit_code', 'audit_passed', 'expected'),
                         [(True, 0, True, 0), (False, 0, True, 1),
                          (True, 1, True, 1), (True, 0, False, 1)])
def test_run_preserves_failures_without_xml_or_protocol(console_workspace, monkeypatch, quality_result,
                                                       quality_passed, unit_code, audit_passed, expected):
    from pmi import quality, performance, audit
    quality_result['passed'] = quality_passed
    monkeypatch.setattr(quality, 'evaluate', lambda dataset, output: copy.deepcopy(quality_result))
    monkeypatch.setattr(performance, 'measure', lambda dataset, output: {
        'passed': True, 'seconds': {'single_resume': .1}, 'limits_seconds': {'single_resume': 120}})
    monkeypatch.setattr(audit, 'scan', lambda root, output: {
        'automated_passed': audit_passed, 'secret_findings': 0, 'contact_candidates': 0 if audit_passed else 1})

    def run(command, **kwargs):
        assert 'pytest' in command
        assert not any('junitxml' in arg for arg in command)
        return subprocess.CompletedProcess(command, unit_code, stdout='1 passed' if not unit_code else '1 failed', stderr='')

    monkeypatch.setattr(cli.subprocess, 'run', run)
    monkeypatch.setattr(sys, 'argv', ['pmi', 'run'])
    assert cli.main() == expected
    assert {path.name for path in console_workspace.iterdir()} == {'inputs'}


def test_live_prints_full_api_metrics_without_report_files(console_workspace, monkeypatch, capsys, quality_result):
    from pmi import live

    def run_live(dataset, output, **kwargs):
        assert output is None
        return {'status': 'passed', 'quality_api': quality_result}

    monkeypatch.setattr(live, 'run_live', run_live)
    monkeypatch.setattr(sys, 'argv', ['pmi', 'live'])
    assert cli.main() == 0
    output = capsys.readouterr().out
    assert 'MongoDB' in output and '0.9401' in output and '0.9228' not in output
    assert {path.name for path in console_workspace.iterdir()} == {'inputs'}


@pytest.mark.parametrize('daemon_available', [False, True])
def test_live_failure_cleans_scratch_without_creating_reports(tmp_path, monkeypatch, daemon_available):
    from pmi import live
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/skills.json').write_text('{}')
    scratch = tmp_path / 'scratch'

    def mkdtemp(**kwargs):
        scratch.mkdir()
        return str(scratch)

    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if command[:2] == ['docker', 'info']:
            return subprocess.CompletedProcess(command, 0 if daemon_available else 1, '{}', '')
        if 'up' in command:
            raise subprocess.CalledProcessError(1, command, stderr='Test startup failure')
        return subprocess.CompletedProcess(command, 0, '', '')

    monkeypatch.setattr(live.tempfile, 'mkdtemp', mkdtemp)
    monkeypatch.setattr(live, 'verify', lambda _: {'ok': True, 'errors': []})
    monkeypatch.setattr(live.subprocess, 'run', run)
    report = live.run_live(tmp_path / 'inputs')
    assert report['status'] != 'passed'
    assert not scratch.exists()
    assert {path.name for path in tmp_path.iterdir()} == {'config'}
    if daemon_available:
        assert 'Test startup failure' in report['reason']
        assert any('down' in command and '--volumes' in command for command in commands)
