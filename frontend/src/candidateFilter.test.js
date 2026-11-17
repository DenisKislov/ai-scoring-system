import { effectiveThreshold, filterCandidates, overlapRatio } from './candidateFilter';

const candidate = (matched, missing) => ({matched_skills: matched, missing_skills: missing});

test('includes the leading candidate even below the calibrated target', () => {
  const top = candidate(['Python'], ['SQL', 'Docker']);
  const other = candidate([], ['Python', 'SQL', 'Docker']);
  expect(effectiveThreshold([top, other], 0.8)).toBe(1 / 3);
  expect(filterCandidates([top, other], 0.8)).toEqual([top]);
});

test('retains candidates exactly at the threshold', () => {
  const top = candidate(['Python'], []);
  const half = candidate(['Python'], ['Docker']);
  expect(filterCandidates([top, half], 0.5)).toEqual([top, half]);
});

test('does not double count missing critical skills', () => {
  expect(overlapRatio({...candidate(['Python'], ['Docker']), missing_critical: ['Docker']})).toBe(0.5);
});

test('handles an unavailable threshold and a zero-coverage pool', () => {
  const all = [candidate([], ['Python'])];
  expect(filterCandidates(all, null)).toEqual(all);
  expect(filterCandidates(all, .8)).toEqual(all);
  expect(filterCandidates([], .8)).toEqual([]);
});
