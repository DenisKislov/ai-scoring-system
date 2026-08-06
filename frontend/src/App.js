import React, { useState, useEffect } from 'react';
import { api } from './api/api';
import './App.css';

function App() {
  const [vacancies, setVacancies] = useState([]);
  const [selectedVacancy, setSelectedVacancy] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState(null);

  useEffect(() => {
    const loadVacancies = async () => {
      try {
        const data = await api.getVacancies();
        if (Array.isArray(data)) {
          setVacancies(data);
        } else {
          setVacancies([]);
        }
      } catch (error) {
        console.error('Ошибка загрузки вакансий:', error);
        setVacancies([]);
      }
    };
    loadVacancies();
  }, []);

  const handleScoring = async (vacancyId) => {
    if (!vacancyId) return;
    
    setLoading(true);
    setCandidates([]);
    setSelectedCandidate(null);
    
    try {
      await api.runScoring(vacancyId);
      const results = await api.getResults(vacancyId, 20);
      
      let candidatesArray = [];
      if (Array.isArray(results)) {
        candidatesArray = results;
      } else if (results && typeof results === 'object') {
        if (Array.isArray(results.results)) {
          candidatesArray = results.results;
        } else if (Array.isArray(results.data)) {
          candidatesArray = results.data;
        } else {
          for (const key in results) {
            if (Array.isArray(results[key])) {
              candidatesArray = results[key];
              break;
            }
          }
        }
      }
      
      setCandidates(candidatesArray);
      if (candidatesArray.length === 0) {
        alert('Нет результатов для этой вакансии');
      }
    } catch (error) {
      console.error('Ошибка при скоринге:', error);
      setCandidates([]);
      alert('Не удалось выполнить скоринг. Проверьте, что бэкенд запущен.');
    } finally {
      setLoading(false);
    }
  };

  const sendFeedback = async (resumeId, decision) => {
    try {
      const response = await fetch(`http://127.0.0.1:8000/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vacancy_id: selectedVacancy,
          resume_id: resumeId,
          decision: decision
        })
      });
      
      if (response.ok) {
        alert('Спасибо за обратную связь!');
        setSelectedCandidate(null);
      } else {
        alert('Не удалось отправить фидбек');
      }
    } catch (error) {
      console.error('Ошибка фидбека:', error);
      alert('Ошибка при отправке');
    }
  };

  const getRankColor = (index) => {
    if (index === 0) return 'gold';
    if (index === 1) return 'silver';
    if (index === 2) return 'bronze';
    return '';
  };

  const getScoreColor = (score) => {
    if (score >= 70) return 'high';
    if (score >= 40) return 'medium';
    return 'low';
  };

  return (
    <div className="app">
      <header>
        <h1>
          <span className="highlight">AI Скоринг</span>
        </h1>
      </header>

      <main>
        <section className="vacancies">
          <label>Вакансии</label>
          <select 
            value={selectedVacancy || ''}
            onChange={(e) => setSelectedVacancy(e.target.value)}
          >
            <option value="">Выберите вакансию</option>
            {Array.isArray(vacancies) && vacancies.map((v) => (
              <option key={v._id} value={v._id}>
                {v.title || 'Без названия'}
              </option>
            ))}
          </select>
          <button 
            onClick={() => handleScoring(selectedVacancy)}
            disabled={!selectedVacancy || loading}
          >
            {loading ? (
              <>
                <span className="loading-spinner"></span>
                Загрузка...
              </>
            ) : (
              'Рассчитать скоринг'
            )}
          </button>
        </section>

        <section className="results">
          <div className="results-header">
            <h2>Рейтинг кандидатов</h2>
            {Array.isArray(candidates) && candidates.length > 0 && (
              <span className="count">{candidates.length} кандидатов</span>
            )}
          </div>

          <div className="table-wrapper">
            {!Array.isArray(candidates) || candidates.length === 0 ? (
              <div className="empty-state">
                <h3>Нет результатов</h3>
                <p>Выберите вакансию и нажмите «Рассчитать скоринг»</p>
              </div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Кандидат</th>
                    <th>Score</th>
                    <th>Опыт</th>
                    <th>Навыки</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((c, index) => {
                    const sticker = null;
                    return (
                      <tr 
                        key={c.resume_id || c._id || index}
                        onClick={() => setSelectedCandidate(c)}
                      >
                        <td className={`rank ${getRankColor(index)}`}>
                          #{index + 1}
                        </td>
                        <td>
                          <strong>{c.candidate_name || 'Кандидат'}</strong>
                        </td>
                        <td className="score-cell">
                          <div className="score-bar-wrapper">
                            <span>{c.score || 0}%</span>
                            <div className="score-bar">
                              <div 
                                className={`score-bar-fill ${getScoreColor(c.score || 0)}`}
                                style={{ width: `${c.score || 0}%` }}
                              ></div>
                            </div>
                          </div>
                        </td>
                        <td className="experience">
                          {c.experience_years || 0} лет
                        </td>
                        <td>
                          <div className="skills-list">
                            {(c.matched_skills || []).slice(0, 6).map((skill, i) => (
                              <span key={i} className="skill-tag">
                                {skill}
                              </span>
                            ))}
                            {(c.matched_skills || []).length > 6 && (
                              <span className="skill-tag more">
                                +{(c.matched_skills || []).length - 6}
                              </span>
                            )}
                            {(c.matched_skills || []).length === 0 && (
                              <span style={{ color: '#9a7aaa', fontSize: '13px' }}>
                                Нет совпадений
                              </span>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </section>

        {selectedCandidate && (
          <div className="modal-overlay" onClick={() => setSelectedCandidate(null)}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <button className="modal-close" onClick={() => setSelectedCandidate(null)}>
                ✕
              </button>
              
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
                <div className="modal-item">
                  <label>Ранг</label>
                  <span>Топ-{candidates.findIndex(c => c.resume_id === selectedCandidate.resume_id) + 1 || '?'}</span>
                </div>
              </div>
              
              <div className="modal-skills">
                <label>Найденные навыки</label>
                <div className="skills-list">
                  {(selectedCandidate.matched_skills || []).map((skill, i) => (
                    <span key={i} className="skill-tag">{skill}</span>
                  ))}
                </div>
              </div>
              
              <div className="modal-skills">
                <label>Отсутствующие навыки</label>
                <div className="skills-list">
                  {(selectedCandidate.missing_skills || []).map((skill, i) => (
                    <span key={i} className="skill-tag missing">{skill}</span>
                  ))}
                </div>
              </div>

              <div className="modal-feedback">
                <button className="yes" onClick={() => sendFeedback(selectedCandidate.resume_id, 'yes')}>
                  Релевантен
                </button>
                <button className="no" onClick={() => sendFeedback(selectedCandidate.resume_id, 'no')}>
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