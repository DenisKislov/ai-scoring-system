export const API_BASE = process.env.REACT_APP_API_URL || `${window.location.protocol}//${window.location.hostname}:8000`;
const API_URL = API_BASE;

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
      throw error;
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
      throw error;
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
      throw error;
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
