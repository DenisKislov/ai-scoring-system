import React, { useState, useEffect } from 'react';
import { api } from './api/api';
import './App.css';

const API_BASE = 'http://127.0.0.1:8000';

function App() {
  const [vacancies, setVacancies] = useState([]);
  const [selectedVacancy, setSelectedVacancy] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [isUploading, setIsUploading] = useState(false);

  const [feedbackMap, setFeedbackMap] = useState({});
  const [fullResumeText, setFullResumeText] = useState(null);
  const [criticalSkills, setCriticalSkills] = useState([]);

  const [logs, setLogs] = useState([]);
  const [metrics, setMetrics] = useState({
    precision: 0,
    recall: 0,
    f1: 0,
    avgScore: 0,
    totalScored: 0,
  });

  const addLog = (type, message) => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs((prev) => [{ timestamp, type, message }, ...prev.slice(0, 49)]);
  };

  const handleClearLogs = () => setLogs([]);

  const loadVacancies = async () => {
    try {
      const data = await api.getVacancies();
      setVacancies(Array.isArray(data) ? data : []);
    } catch (error) {
      addLog('ERROR', `Ошибка загрузки вакансий: ${error.message}`);
      setVacancies([]);
    }
  };

  useEffect(() => {
    loadVacancies();
    addLog('INFO', 'Приложение инициализировано.');
  }, []);

  useEffect(() => {
    setCriticalSkills([]);
  }, [selectedVacancy]);

  const handleUploadResumes = async (event) => {
    const files = Array.from(event.target.files);
    if (files.length === 0) return;
    setIsUploading(true);
    for (const file of files) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        const response = await fetch(`${API_BASE}/upload_resume`, { method: 'POST', body: formData });
        const data = await response.json();
        if (response.ok) {
          addLog('SUCCESS', `[Резюме] '${data.filename}' | Навыки: ${data.skills_count}`);
        } else {
          addLog('WARN', `Файл '${file.name}': ${data.detail || 'Ошибка'}`);
        }
      } catch (error) {
        addLog('ERROR', `Сбой для '${file.name}': ${error.message}`);
      }
    }
    setIsUploading(false);
    event.target.value = null;
  };

  const handleUploadVacancies = async (event) => {
    const files = Array.from(event.target.files);
    if (files.length === 0) return;
    setIsUploading(true);
    for (const file of files) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        const response = await fetch(`${API_BASE}/upload_vacancy`, { method: 'POST', body: formData });
        const data = await response.json();
        if (response.ok) {
          addLog('SUCCESS', `[Вакансия] '${data.filename}' | Навыки: ${data.skills_count}`);
        } else {
          addLog('WARN', `Вакансия '${file.name}': ${data.detail}`);
        }
      } catch (error) {
        addLog('ERROR', `Сбой для '${file.name}': ${error.message}`);
      }
    }
    await loadVacancies();
    setIsUploading(false);
    event.target.value = null;
  };

  const handleClearResumes = async () => {
    if (!window.confirm('Удалить ВСЕ резюме?')) return;
    setIsUploading(true);
    try {
      const response = await fetch(`${API_BASE}/resumes/clear`, { method: 'DELETE' });
      if (response.ok) {
        const data = await response.json();
        addLog('WARN', `Удалено резюме: ${data.deleted_count}`);
        alert(`Удалено резюме: ${data.deleted_count}`);
        setCandidates([]);
        setMetrics({ precision: 0, recall: 0, f1: 0, avgScore: 0, totalScored: 0 });
      }
    } finally {
      setIsUploading(false);
    }
  };

  const handleClearVacancies = async () => {
    if (!window.confirm('Удалить ВСЕ вакансии?')) return;
    setIsUploading(true);
    try {
      const response = await fetch(`${API_BASE}/vacancies/clear`, { method: 'DELETE' });
      if (response.ok) {
        const data = await response.json();
        addLog('WARN', `Удалено вакансий: ${data.deleted_count}`);
        alert(`Удалено вакансий: ${data.deleted_count}`);
        await loadVacancies();
        setSelectedVacancy(null);
      }
    } finally {
      setIsUploading(false);
    }
  };

  const handleGenerateSyntheticData = async () => {
    setIsUploading(true);
    addLog('INFO', 'Генерация синтетических данных...');
    try {
      const response = await fetch(`${API_BASE}/generate_test_data?vacancies=5&resumes=20`, { method: 'POST' });
      if (response.ok) {
        addLog('SUCCESS', 'Датасет сгенерирован');
        alert('Синтетические данные созданы!');
        await loadVacancies();
      } else {
        addLog('ERROR', 'Ошибка генерации');
      }
    } catch (e) {
      addLog('ERROR', `Сетевая ошибка: ${e.message}`);
    } finally {
      setIsUploading(false);
    }
  };

  const handleImportSuperJobData = async () => {
    setIsUploading(true);
    addLog('INFO', 'Импорт вакансий SuperJob...');
    try {
      const response = await fetch(`${API_BASE}/import_superjob_vacancies`, { method: 'POST' });
      if (response.ok) {
        const data = await response.json();
        addLog('SUCCESS', `Импортировано вакансий: ${data.imported_vacancies}`);
        alert(`Импортировано вакансий: ${data.imported_vacancies || 'все'}`);
        await loadVacancies();
      } else {
        addLog('ERROR', 'Ошибка импорта');
      }
    } catch (e) {
      addLog('ERROR', `Сетевая ошибка: ${e.message}`);
    } finally {
      setIsUploading(false);
    }
  };

  const handleImportSuperJobResumes = async () => {
    setIsUploading(true);
    addLog('INFO', 'Импорт резюме SuperJob...');
    try {
      const response = await fetch(`${API_BASE}/import_superjob_resumes`, { method: 'POST' });
      if (response.ok) {
        const data = await response.json();
        addLog('SUCCESS', `Загружено резюме: ${data.imported_resumes}`);
        alert(`Импортировано резюме: ${data.imported_resumes}`);
      } else {
        const err = await response.json();
        addLog('WARN', `Ошибка: ${err.detail}`);
      }
    } catch (e) {
      addLog('ERROR', `Сетевая ошибка: ${e.message}`);
    } finally {
      setIsUploading(false);
    }
  };

  const handleViewResumeText = async (resumeId) => {
    try {
      const response = await fetch(`${API_BASE}/resumes/${resumeId}`);
      if (response.ok) {
        const data = await response.json();
        setFullResumeText(data._raw_text || data.formatted_text || 'Текст не найден.');
      }
    } catch (error) {
      addLog('ERROR', `Ошибка загрузки: ${error.message}`);
    }
  };

  const handleScoring = async (vacancyId) => {
    if (!vacancyId) {
      addLog('WARN', 'Вакансия не выбрана');
      return;
    }

    const currentVac = vacancies.find((v) => v._id === vacancyId);
    const reqSkills = currentVac ? currentVac.skills || [] : [];

    setLoading(true);
    setCandidates([]);
    setSelectedCandidate(null);
    addLog('INFO', `Старт скоринга: '${currentVac?.title || vacancyId}'`);

    try {
      const scoreRes = await fetch(`${API_BASE}/score`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vacancy_id: vacancyId,
          limit_resumes: 5000,
          critical_skills: criticalSkills.length > 0 ? criticalSkills : undefined,
        }),
      });

      const scoreMeta = await scoreRes.json();

      if (!scoreRes.ok) {
        addLog('ERROR', `Сбой скоринга: ${scoreMeta.detail || 'Ошибка'}`);
        return;
      }

      const results = await api.getResults(vacancyId, 5000);
      let candidatesArray = Array.isArray(results) ? results : results.results || results.data || [];

      candidatesArray.sort((a, b) => {
        if (b.score !== a.score) return (b.score || 0) - (a.score || 0);
        return (b.experience_years || 0) - (a.experience_years || 0);
      });

      setCandidates(candidatesArray);

      const scoresSum = candidatesArray.reduce((acc, c) => acc + (c.score || 0), 0);
      const avgScore = candidatesArray.length > 0 ? Math.round(scoresSum / candidatesArray.length) : 0;

      let totalMatched = 0;
      let totalCandidateSkills = 0;
      let totalVacancySkills = 0;

      candidatesArray.forEach((c) => {
        const matched = (c.matched_skills || []).length;
        const missing = (c.missing_skills || []).length;
        totalMatched += matched;
        totalCandidateSkills += matched + 2;
        totalVacancySkills += matched + missing || reqSkills.length || 5;
      });

      const precision = totalCandidateSkills > 0 ? Number((totalMatched / totalCandidateSkills).toFixed(2)) : 0;
      const recall = totalVacancySkills > 0 ? Number((totalMatched / totalVacancySkills).toFixed(2)) : 0;
      const f1 = precision + recall > 0 ? Number(((2 * (precision * recall)) / (precision + recall)).toFixed(2)) : 0;

      setMetrics({
        precision: scoreMeta.metrics?.precision || precision,
        recall: scoreMeta.metrics?.recall || recall,
        f1: scoreMeta.metrics?.f1 || f1,
        avgScore: scoreMeta.metrics?.avg_score || avgScore,
        totalScored: scoreMeta.scored_count || candidatesArray.length,
      });

      addLog('SUCCESS', `Оценено: ${candidatesArray.length} | P=${precision}, R=${recall}, F1=${f1}`);

    } catch (error) {
      addLog('ERROR', `Ошибка скоринга: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const sendFeedback = async (resumeId, decision) => {
    try {
      const response = await fetch(`${API_BASE}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vacancy_id: selectedVacancy, resume_id: resumeId, decision }),
      });
      if (response.ok) {
        setFeedbackMap((prev) => ({ ...prev, [resumeId]: decision }));
        addLog('INFO', `Фидбек: ${decision}`);
      }
    } catch (error) {
      addLog('ERROR', `Ошибка фидбека: ${error.message}`);
    }
  };

  const handleCandidateClick = (c) => {
    setSelectedCandidate(c);
    setFullResumeText(null);
  };

  const closeModal = () => {
    setSelectedCandidate(null);
    setFullResumeText(null);
  };

  const getRankColor = (index) => {
    if (index === 0) return 'gold';
    if (index === 1) return 'silver';
    if (index === 2) return 'bronze';
    return '';
  };

  const currentVacancyObj = vacancies.find((v) => v._id === selectedVacancy);

  return (
    <div className="app">
      <header>
        <div>
          <h1><span className="highlight">Скоринг</span></h1>
        </div>
      </header>

      <div style={{
        marginBottom: '25px',
        padding: '18px 20px',
        backgroundColor: '#4a4a4a',
        color: '#ffffff',
        border: '1px solid #4a4a4a'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px', borderBottom: '1px solid #ffffff', paddingBottom: '10px' }}>
          <span style={{ fontWeight: 700, fontSize: '15px', color: '#ffffff' }}>ТЕСТОВАЯ ПАНЕЛЬ</span>
          <span style={{ fontSize: '12px', color: '#e0e0e0' }}>MongoDB & Scorer Engine</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px' }}>

          <div>
            <div style={{ fontSize: '13px', fontWeight: 'bold', marginBottom: '10px', color: '#ffffff' }}>1. Тестовые датасеты</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <button
                onClick={handleGenerateSyntheticData}
                disabled={isUploading}
                style={{
                  backgroundColor: '#ffffff',
                  color: '#4a4a4a',
                  border: '1px solid #ffffff',
                  padding: '9px 12px',
                  cursor: 'pointer',
                  fontWeight: '600',
                  fontSize: '13px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center'
                }}
              >
                <span>Синтетический генератор</span>
                <span style={{ fontSize: '11px' }}>(5 / 20)</span>
              </button>

              <button
                onClick={handleImportSuperJobData}
                disabled={isUploading}
                style={{
                  backgroundColor: '#ffffff',
                  color: '#4a4a4a',
                  border: '1px solid #ffffff',
                  padding: '9px 12px',
                  cursor: 'pointer',
                  fontWeight: '600',
                  fontSize: '13px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center'
                }}
              >
                <span>Вакансии SuperJob</span>
                <span style={{ fontSize: '11px' }}>(51)</span>
              </button>

              <button
                onClick={handleImportSuperJobResumes}
                disabled={isUploading}
                style={{
                  backgroundColor: '#ffffff',
                  color: '#4a4a4a',
                  border: '1px solid #ffffff',
                  padding: '9px 12px',
                  cursor: 'pointer',
                  fontWeight: '600',
                  fontSize: '13px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center'
                }}
              >
                <span>Резюме SuperJob</span>
                <span style={{ fontSize: '11px' }}>(JSON)</span>
              </button>
            </div>
          </div>

          <div>
            <div style={{ fontSize: '13px', fontWeight: 'bold', marginBottom: '10px', color: '#ffffff' }}>2. Метрики</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
              <div style={{ backgroundColor: '#ffffff', padding: '10px', textAlign: 'center', border: '1px solid #ffffff' }}>
                <div style={{ fontSize: '10px', color: '#4a4a4a', textTransform: 'uppercase' }}>Precision</div>
                <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#4a4a4a', marginTop: '4px' }}>{metrics.precision}</div>
              </div>
              <div style={{ backgroundColor: '#ffffff', padding: '10px', textAlign: 'center', border: '1px solid #ffffff' }}>
                <div style={{ fontSize: '10px', color: '#4a4a4a', textTransform: 'uppercase' }}>Recall</div>
                <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#4a4a4a', marginTop: '4px' }}>{metrics.recall}</div>
              </div>
              <div style={{ backgroundColor: '#ffffff', padding: '10px', textAlign: 'center', border: '1px solid #ffffff' }}>
                <div style={{ fontSize: '10px', color: '#4a4a4a', textTransform: 'uppercase' }}>F1</div>
                <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#4a4a4a', marginTop: '4px' }}>{metrics.f1}</div>
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px', fontSize: '11px', color: '#e0e0e0' }}>
              <span>Оценено: <strong style={{ color: '#ffffff' }}>{metrics.totalScored}</strong></span>
              <span>Средний Score: <strong style={{ color: '#ffffff' }}>{metrics.avgScore}%</strong></span>
            </div>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <span style={{ fontSize: '13px', fontWeight: 'bold', color: '#ffffff' }}>3. Логи</span>
              <button
                onClick={handleClearLogs}
                style={{ background: 'none', border: 'none', color: '#e0e0e0', fontSize: '11px', cursor: 'pointer', textDecoration: 'underline' }}
              >
                очистить
              </button>
            </div>
            <div style={{
              backgroundColor: '#ffffff',
              padding: '8px 12px',
              fontFamily: 'monospace',
              fontSize: '11px',
              height: '80px',
              overflowY: 'auto',
              border: '1px solid #ffffff'
            }}>
              {logs.length === 0 ? (
                <div style={{ color: '#4a4a4a' }}>Логи пусты...</div>
              ) : (
                logs.map((log, index) => (
                  <div key={index} style={{ marginBottom: '4px', lineHeight: '1.4', color: '#4a4a4a' }}>
                    <span>[{log.timestamp}]</span>{' '}
                    <span style={{ fontWeight: 'bold' }}>{log.type}:</span>{' '}
                    <span>{log.message}</span>
                  </div>
                ))
              )}
            </div>
          </div>

        </div>
      </div>

      <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#ffffff', border: '1px solid #4a4a4a', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '20px', alignItems: 'center' }}>
        <div>
          <h3 style={{ marginTop: 0, marginBottom: '10px', color: '#4a4a4a' }}>Пользовательские файлы</h3>
          <div style={{ display: 'flex', gap: '20px' }}>
            <div>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold', fontSize: '14px', color: '#4a4a4a' }}>Резюме</label>
              <label
                htmlFor="resume-upload"
                style={{
                  display: 'inline-block',
                  backgroundColor: '#4a4a4a',
                  color: '#ffffff',
                  padding: '8px 18px',
                  fontSize: '14px',
                  fontWeight: '600',
                  cursor: 'pointer',
                  border: '1px solid #4a4a4a',
                }}
              >
                Выбрать файлы
              </label>
              <input id="resume-upload" type="file" multiple accept=".pdf,.txt" onChange={handleUploadResumes} disabled={isUploading} style={{ display: 'none' }} />
              <span style={{ fontSize: '13px', color: '#4a4a4a', marginLeft: '10px' }}>
                {isUploading ? 'Загрузка...' : 'файлы не выбраны'}
              </span>
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold', fontSize: '14px', color: '#4a4a4a' }}>Вакансии</label>
              <label
                htmlFor="vacancy-upload"
                style={{
                  display: 'inline-block',
                  backgroundColor: '#4a4a4a',
                  color: '#ffffff',
                  padding: '8px 18px',
                  fontSize: '14px',
                  fontWeight: '600',
                  cursor: 'pointer',
                  border: '1px solid #4a4a4a',
                }}
              >
                Выбрать файлы
              </label>
              <input id="vacancy-upload" type="file" multiple accept=".pdf,.txt" onChange={handleUploadVacancies} disabled={isUploading} style={{ display: 'none' }} />
              <span style={{ fontSize: '13px', color: '#4a4a4a', marginLeft: '10px' }}>
                {isUploading ? 'Загрузка...' : 'файлы не выбраны'}
              </span>
            </div>
          </div>
        </div>

        <div style={{ paddingLeft: '20px', borderLeft: '1px solid #4a4a4a' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <button
              onClick={handleClearResumes}
              disabled={isUploading}
              style={{
                backgroundColor: '#e0e0e0',
                color: '#4a4a4a',
                border: '1px solid #4a4a4a',
                padding: '8px 12px',
                cursor: 'pointer',
                fontWeight: 'bold',
              }}
            >
              Удалить резюме
            </button>
            <button
              onClick={handleClearVacancies}
              disabled={isUploading}
              style={{
                backgroundColor: '#e0e0e0',
                color: '#4a4a4a',
                border: '1px solid #4a4a4a',
                padding: '8px 12px',
                cursor: 'pointer',
                fontWeight: 'bold',
              }}
            >
              Удалить вакансии
            </button>
          </div>
        </div>
      </div>

      <main>
        <section className="vacancies">
          <label>Вакансии</label>
          <select value={selectedVacancy || ''} onChange={(e) => setSelectedVacancy(e.target.value)}>
            <option value="">Выберите вакансию</option>
            {Array.isArray(vacancies) && vacancies.map((v) => (
              <option key={v._id} value={v._id}>{`${v.title} (ID: ${v._id.slice(-4)})`}</option>
            ))}
          </select>

          {currentVacancyObj && currentVacancyObj.skills && currentVacancyObj.skills.length > 0 && (
            <div style={{ marginTop: '15px', padding: '15px', backgroundColor: '#e0e0e0', border: '1px solid #4a4a4a' }}>
              <label style={{ fontWeight: 'bold', color: '#4a4a4a', display: 'block', marginBottom: '10px' }}>
                Отметьте критические навыки (вес ×2):
              </label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                {currentVacancyObj.skills.map((skill) => (
                  <label key={skill} style={{ display: 'flex', alignItems: 'center', gap: '5px', backgroundColor: criticalSkills.includes(skill) ? '#4a4a4a' : '#ffffff', color: criticalSkills.includes(skill) ? '#ffffff' : '#4a4a4a', border: '1px solid #4a4a4a', padding: '5px 10px', cursor: 'pointer', fontSize: '13px' }}>
                    <input
                      type="checkbox"
                      checked={criticalSkills.includes(skill)}
                      onChange={(e) => {
                        if (e.target.checked) setCriticalSkills([...criticalSkills, skill]);
                        else setCriticalSkills(criticalSkills.filter(s => s !== skill));
                      }}
                      style={{ margin: 0 }}
                    />
                    <span style={{ fontWeight: criticalSkills.includes(skill) ? 'bold' : 'normal' }}>{skill}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          <button
            onClick={() => handleScoring(selectedVacancy)}
            disabled={!selectedVacancy || loading}
            style={{ marginTop: '15px' }}
          >
            {loading ? 'Загрузка...' : 'Рассчитать скоринг'}
          </button>
        </section>

        <section className="results">
          <div className="results-header">
            <h2>Рейтинг кандидатов</h2>
            {Array.isArray(candidates) && candidates.length > 0 && <span className="count">{candidates.length} кандидатов</span>}
          </div>

          <div className="table-wrapper">
            {!Array.isArray(candidates) || candidates.length === 0 ? (
              <div className="empty-state">
                <h3>Нет результатов</h3>
                <p>Выберите вакансию и нажмите «Рассчитать скоринг»</p>
              </div>
            ) : (
              <table style={{ animation: 'fadeSlideUp 0.5s ease forwards' }}>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Кандидат</th>
                    <th>Score</th>
                    <th>Опыт</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((c, index) => (
                    <tr key={c.resume_id || c._id || index} onClick={() => handleCandidateClick(c)}>
                      <td className={`rank ${getRankColor(index)}`}>#{index + 1}</td>
                      <td><strong>{c.candidate_name || 'Кандидат'}</strong></td>
                      <td className="score-cell">{c.score || 0}%</td>
                      <td className="experience">{c.experience_years || 0} лет</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        {selectedCandidate && (
          <div className="modal-overlay" onClick={closeModal}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <button className="modal-close" onClick={closeModal}>✕</button>
              <h2>{selectedCandidate.candidate_name || 'Кандидат'}</h2>

              <div className="modal-grid">
                <div className="modal-item">
                  <label>Score</label>
                  <span className="modal-score">{selectedCandidate.score || 0}%</span>
                </div>
                <div className="modal-item">
                  <label>Опыт</label>
                  <span>{selectedCandidate.experience_years || 0} лет</span>
                </div>
              </div>

              <div className="modal-skills">
                <label>Совпадающие навыки</label>
                <div className="skills-list">
                  {[...new Set(selectedCandidate.matched_skills || [])].map((skill, i) => (
                    <span key={i} className="skill-tag">{skill}</span>
                  ))}
                  {[...new Set(selectedCandidate.matched_skills || [])].length === 0 && (
                    <span style={{ color: '#4a4a4a', fontSize: '13px' }}>Нет совпадений</span>
                  )}
                </div>
              </div>

              {selectedCandidate.missing_critical && selectedCandidate.missing_critical.length > 0 && (
                <div className="modal-skills" style={{ marginTop: '15px' }}>
                  <label style={{ color: '#4a4a4a', fontWeight: 'bold' }}>Критические пробелы:</label>
                  <div className="skills-list">
                    {selectedCandidate.missing_critical.map((skill, i) => (
                      <span key={i} className="skill-tag" style={{ backgroundColor: '#4a4a4a', color: '#ffffff' }}>{skill}</span>
                    ))}
                  </div>
                </div>
              )}

              <div className="modal-skills" style={{ marginTop: '15px' }}>
                <label>Остальные недостающие навыки</label>
                <div className="skills-list">
                  {(selectedCandidate.missing_skills || []).map((skill, i) => (
                    <span key={i} className="skill-tag missing">{skill}</span>
                  ))}
                </div>
              </div>

              <div style={{ marginTop: '20px', borderTop: '1px solid #4a4a4a', paddingTop: '15px' }}>
                {!fullResumeText ? (
                  <button
                    onClick={() => handleViewResumeText(selectedCandidate.resume_id)}
                    style={{
                      width: '100%',
                      padding: '10px',
                      backgroundColor: '#e0e0e0',
                      border: '1px solid #4a4a4a',
                      cursor: 'pointer',
                      fontWeight: 'bold',
                      color: '#4a4a4a',
                    }}
                  >
                    Посмотреть текст резюме
                  </button>
                ) : (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
                      <label>Оригинальный текст:</label>
                      <button onClick={() => setFullResumeText(null)} style={{ background: 'none', border: 'none', color: '#4a4a4a', cursor: 'pointer', textDecoration: 'underline' }}>Скрыть</button>
                    </div>
                    <div style={{ backgroundColor: '#e0e0e0', border: '1px solid #4a4a4a', padding: '15px', maxHeight: '300px', overflowY: 'auto', fontSize: '13px', whiteSpace: 'pre-wrap' }}>
                      {fullResumeText}
                    </div>
                  </div>
                )}
              </div>

              <div className="modal-feedback">
                <button
                  onClick={() => sendFeedback(selectedCandidate.resume_id, 'yes')}
                  style={{ backgroundColor: feedbackMap[selectedCandidate.resume_id] === 'yes' ? '#4a4a4a' : '#ffffff', color: feedbackMap[selectedCandidate.resume_id] === 'yes' ? '#ffffff' : '#4a4a4a' }}
                >
                  Релевантен
                </button>
                <button
                  onClick={() => sendFeedback(selectedCandidate.resume_id, 'no')}
                  style={{ backgroundColor: feedbackMap[selectedCandidate.resume_id] === 'no' ? '#4a4a4a' : '#ffffff', color: feedbackMap[selectedCandidate.resume_id] === 'no' ? '#ffffff' : '#4a4a4a' }}
                >
                  Нерелевантен
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;