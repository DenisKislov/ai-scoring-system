import { render, screen, within, waitFor, act } from '@testing-library/react';
import rawUserEvent from '@testing-library/user-event';
import App from './App';

const originalFetch = global.fetch;
// user-event v13 needs an explicit async act boundary with React 19.
const userEvent = Object.fromEntries(['click', 'type', 'selectOptions'].map(name =>
  [name, (...args) => act(async () => { await rawUserEvent[name](...args); })]));

beforeEach(() => {
  global.fetch = jest.fn(async (url) => {
    const path = new URL(url).pathname;
    const initialResponses = {
      '/vacancies': [],
      '/stats': { vacancies: 0, resumes: 0 },
      '/threshold': { value: null },
    };
    if (!(path in initialResponses)) throw new Error(`Unexpected request: ${url}`);
    return { ok: true, json: async () => initialResponses[path] };
  });
});

afterEach(() => {
  global.fetch = originalFetch;
});

test('renders scoring app title', async () => {
  render(<App />);
  expect(screen.getByRole('heading', { name: /скоринг/i })).toBeInTheDocument();
  await screen.findByText(/На бэкенде не задан/);
});

test('scores a selected vacancy, filters candidates and highlights literal skills in the resume', async () => {
  const results = [
    {
      resume_id: 'resume1',
      score: 84,
      experience_years: 5,
      matched_skills: ['C++', '.NET'],
      missing_skills: ['SQL'],
      missing_critical: ['SQL'],
    },
    {
      resume_id: 'resume2',
      score: 40,
      experience_years: 2,
      matched_skills: ['C++'],
      missing_skills: ['.NET', 'SQL'],
      missing_critical: ['SQL'],
    },
  ];
  const responses = {
    '/vacancies': [{ _id: 'vacancy1', title: 'C++/.NET developer', skills: ['C++', '.NET', 'SQL'] }],
    '/stats': { vacancies: 1, resumes: 2 },
    '/threshold': { value: 0.6, n_vacancies: 1, n_resumes: 2 },
    '/score': { vacancy_id: 'vacancy1', count: 2, results },
    '/results/vacancy1': { vacancy_id: 'vacancy1', count: 2, results },
    '/feedback': { decision: null, history: [] },
    '/resumes/resume1': { _raw_text: 'Опыт разработки на C++ и .NET; примеры XC++ и XNET.' },
  };
  global.fetch.mockImplementation(async (url) => {
    const path = new URL(url).pathname;
    if (!(path in responses)) throw new Error(`Unexpected request: ${url}`);
    return { ok: true, json: async () => responses[path] };
  });

  const { container } = render(<App />);
  await screen.findByRole('option', { name: /C\+\+\/\.NET developer/ });
  await userEvent.selectOptions(screen.getByRole('combobox'), 'vacancy1');
  await userEvent.click(screen.getByRole('checkbox', { name: 'SQL' }));
  await userEvent.click(screen.getByRole('button', { name: 'Рассчитать скоринг' }));

  const candidate = await screen.findByRole('row', { name: /#1 Кандидат 84%/ });
  expect(screen.queryByRole('row', { name: /40%/ })).not.toBeInTheDocument();
  expect(screen.getByText('1 кандидатов из 2')).toBeInTheDocument();
  const scoreRequest = global.fetch.mock.calls.find(([url]) => url.endsWith('/score'));
  expect(JSON.parse(scoreRequest[1].body)).toMatchObject({
    vacancy_id: 'vacancy1',
    critical_skills: ['SQL'],
  });

  await userEvent.click(candidate);
  expect(screen.getByRole('heading', { name: 'Кандидат' })).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /Посмотреть текст резюме/ }));
  await screen.findByText('Оригинальный текст:');
  expect(screen.getByText('C++', { selector: 'mark' })).toBeInTheDocument();
  expect(screen.getByText('.NET', { selector: 'mark' })).toBeInTheDocument();
  expect(container.querySelectorAll('mark')).toHaveLength(2);
  expect(within(container).queryByText(/Метрики точности скоринга|Precision|Recall|F1-Score/)).not.toBeInTheDocument();
});

test('restores the HR decision after reopening a candidate and displays both dated decisions', async () => {
  const history = [];
  const candidate = { resume_id:'r1', score:90, matched_skills:['Python'], missing_skills:[], keyword_contribution:.85, cosine_contribution:.05 };
  global.fetch.mockImplementation(async (url, options = {}) => {
    const path = new URL(url).pathname;
    let data;
    if (path === '/vacancies') data = [{ _id:'v1', title:'Разработчик', skills:['Python'], critical_skills:['Python'] }];
    else if (path === '/stats') data = { vacancies:1, resumes:1 };
    else if (path === '/threshold') data = { value:null };
    else if (path === '/score' || path === '/results/v1') data = { count:1, results:[candidate] };
    else if (path === '/feedback' && options.method === 'POST') {
      const event = { decision:JSON.parse(options.body).decision, updated_at:'2026-10-21T08:00:00Z' };
      history.push(event); data = { ok:true, event };
    } else if (path === '/feedback') data = { decision:history.at(-1)?.decision, history:[...history] };
    else throw new Error(`Unexpected request: ${url}`);
    return { ok:true, json:async () => data };
  });
  render(<App />);
  await screen.findByRole('option', { name:/Разработчик/ });
  await userEvent.selectOptions(screen.getByRole('combobox'), 'v1');
  expect(screen.getByRole('checkbox', { name:'Python' })).toBeChecked();
  await userEvent.click(screen.getByRole('button', { name:'Рассчитать скоринг' }));
  await userEvent.click(await screen.findByRole('row', { name:/#1 Кандидат 90%/ }));
  await userEvent.click(screen.getByRole('button', { name:'Да' }));
  await screen.findByText('Решение HR: Да');
  await userEvent.click(screen.getByRole('button', { name:'✕' }));
  await userEvent.click(screen.getByRole('row', { name:/#1 Кандидат 90%/ }));
  await screen.findByText('Решение HR: Да');
  await userEvent.click(screen.getByRole('button', { name:'Нет' }));
  await screen.findByText('Решение HR: Нет');
  expect(within(screen.getByRole('list', { name:'История решений HR' })).getAllByRole('listitem')).toHaveLength(2);
  expect(screen.getByText('Вклад навыков')).toBeInTheDocument();
  expect(screen.getByRole('link', { name:'Выгрузить JSON' })).toHaveAttribute('href','http://localhost:8000/results/v1');
});

test('creates a vacancy from the form with critical skills', async () => {
  const initialFetch = global.fetch;
  global.fetch = jest.fn(async (url,options) => {
    if (new URL(url).pathname === '/vacancies' && options?.method === 'POST') {
      return { ok:true, json:async () => ({ _id:'v-new' }) };
    }
    return initialFetch(url,options);
  });
  render(<App />);
  await screen.findByText(/На бэкенде не задан/);
  await userEvent.type(screen.getByLabelText('Название вакансии'),'Разработчик');
  await userEvent.type(screen.getByLabelText('Описание вакансии'),'Разработка сервисов');
  await userEvent.type(screen.getByLabelText('Навыки через запятую'),'Python, PostgreSQL');
  await userEvent.type(screen.getByLabelText('Критические навыки через запятую'),'Python');
  await userEvent.click(screen.getByRole('button', { name:'Сохранить вакансию' }));
  await waitFor(() => expect(screen.getByLabelText('Название вакансии')).toHaveValue(''));
  const call = global.fetch.mock.calls.find(([,options]) => options?.method === 'POST');
  expect(JSON.parse(call[1].body)).toEqual({ title:'Разработчик', description:'Разработка сервисов', skills:['Python','PostgreSQL'], critical_skills:['Python'] });
});

const deferred = () => {
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  return { promise, resolve };
};
const response = data => ({ ok: true, json: async () => data });

function setupReviewScenario(overrides = {}) {
  const rows = [
    { resume_id: 'r1', score: 90, matched_skills: ['Python'] },
    { resume_id: 'r2', score: 80, matched_skills: ['Python'] },
  ];
  global.fetch.mockImplementation(async (url, options = {}) => {
    const path = new URL(url).pathname;
    if (overrides[path]) return overrides[path](url, options);
    const data = {
      '/vacancies': [
        { _id: 'v1', title: 'First vacancy', skills: ['Python'], critical_skills: ['Python'] },
        { _id: 'v2', title: 'Second vacancy', skills: ['Python'], critical_skills: [] },
      ],
      '/stats': { vacancies: 2, resumes: 2 }, '/threshold': { value: null },
      '/score': { results: rows }, '/results/v1': { results: rows }, '/results/v2': { results: rows },
      '/feedback': { decision: null, history: [] },
    };
    if (!(path in data)) throw new Error(`Unexpected ${path}`);
    return response(data[path]);
  });
  return render(<App />);
}

async function selectFirstAndScore() {
  await screen.findByRole('option', { name: /First vacancy/ });
  await userEvent.selectOptions(screen.getByRole('combobox'), 'v1');
  await userEvent.click(screen.getByRole('button', { name: 'Рассчитать скоринг' }));
}

test('sends an empty critical list when all saved critical skills are unchecked', async () => {
  setupReviewScenario();
  await screen.findByRole('option', { name: /First vacancy/ });
  await userEvent.selectOptions(screen.getByRole('combobox'), 'v1');
  await userEvent.click(screen.getByRole('checkbox', { name: 'Python' }));
  await userEvent.click(screen.getByRole('button', { name: 'Рассчитать скоринг' }));
  await screen.findByRole('row', { name: /90%/ });
  const call = global.fetch.mock.calls.find(([url]) => url.endsWith('/score'));
  expect(JSON.parse(call[1].body).critical_skills).toEqual([]);
});

test('ignores a scoring response for a vacancy that is no longer selected', async () => {
  const pending = deferred();
  setupReviewScenario({ '/score': () => pending.promise });
  await selectFirstAndScore();
  await userEvent.selectOptions(screen.getByRole('combobox'), 'v2');
  await act(async () => pending.resolve(response({ results: [{ resume_id: 'r1', score: 90, matched_skills: ['Python'] }] })));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Рассчитать скоринг' })).toBeEnabled());
  expect(screen.queryByRole('row', { name: /90%/ })).not.toBeInTheDocument();
});

test('switching vacancy closes the old candidate card', async () => {
  setupReviewScenario();
  await selectFirstAndScore();
  await userEvent.click(await screen.findByRole('row', { name: /90%/ }));
  await userEvent.selectOptions(screen.getByRole('combobox'), 'v2');
  expect(screen.queryByRole('button', { name: 'Да' })).not.toBeInTheDocument();
});

test('a late resume-text response cannot appear in another candidate card', async () => {
  const pending = deferred();
  setupReviewScenario({ '/resumes/r1': () => pending.promise });
  await selectFirstAndScore();
  await userEvent.click(await screen.findByRole('row', { name: /90%/ }));
  await userEvent.click(screen.getByRole('button', { name: /Посмотреть текст резюме/ }));
  await userEvent.click(screen.getByRole('button', { name: '✕' }));
  await userEvent.click(screen.getByRole('row', { name: /80%/ }));
  await act(async () => pending.resolve(response({ _raw_text: 'PRIVATE TEXT OF FIRST CANDIDATE' })));
  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/resumes/r1')));
  expect(screen.queryByText('PRIVATE TEXT OF FIRST CANDIDATE')).not.toBeInTheDocument();
});

test('reports a failed deletion without presenting it as success', async () => {
  const confirm = jest.spyOn(window, 'confirm').mockReturnValue(true);
  setupReviewScenario({ '/resumes/clear': () => ({ ok: false, status: 503, json: async () => ({ detail: 'DB unavailable' }) }) });
  await screen.findByRole('option', { name: /First vacancy/ });
  await userEvent.click(screen.getByRole('button', { name: 'Удалить резюме' }));
  expect(await screen.findByText(/Ошибка удаления резюме/)).toBeInTheDocument();
  confirm.mockRestore();
});

test('a late HR save cannot change the decision or history in another card', async () => {
  const pending = deferred();
  setupReviewScenario({ '/feedback': (url, options) => options.method === 'POST'
    ? pending.promise : response({ decision: null, history: [] }) });
  await selectFirstAndScore();
  await userEvent.click(await screen.findByRole('row', { name: /90%/ }));
  await userEvent.click(screen.getByRole('button', { name: 'Да' }));
  expect(screen.getByRole('button', { name: 'Нет' })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: '✕' }));
  await userEvent.click(screen.getByRole('row', { name: /80%/ }));
  await act(async () => pending.resolve(response({ event: { decision: 'yes', updated_at: '2026-10-26T00:00:00Z' } })));
  expect(screen.getByText('Решение HR: Не задано')).toBeInTheDocument();
  expect(within(screen.getByRole('list', { name: 'История решений HR' })).queryAllByRole('listitem')).toHaveLength(0);
});

test('reports a failed vacancy load instead of silently showing an empty database', async () => {
  const log = jest.spyOn(console, 'error').mockImplementation(() => {});
  setupReviewScenario({ '/vacancies': () => ({ ok: false, status: 503 }) });
  expect(await screen.findByText(/Ошибка загрузки вакансий:.*503/)).toBeInTheDocument();
  log.mockRestore();
});
