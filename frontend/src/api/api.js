const API_URL = 'http://127.0.0.1:8000';

export const api = {
  getVacancies: async () => {
    try {
      const response = await fetch(`${API_URL}/vacancies`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Ошибка в getVacancies:', error);
      return [];
    }
  },

  getResults: async (vacancyId, limit = 5000) => {
    try {
      const response = await fetch(`${API_URL}/results/${vacancyId}?top=${limit}`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Ошибка в getResults:', error);
      return [];
    }
  },

  getResume: async (resumeId) => {
    try {
      const response = await fetch(`${API_URL}/resumes/${resumeId}`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Ошибка в getResume:', error);
      return null;
    }
  },

  postFeedback: async (vacancyId, resumeId, decision) => {
    try {
      const response = await fetch(`${API_URL}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vacancy_id: vacancyId,
          resume_id: resumeId,
          decision: decision,
        }),
      });
      return response.ok;
    } catch (error) {
      console.error('Ошибка в postFeedback:', error);
      return false;
    }
  },
};