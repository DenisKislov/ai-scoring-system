export const overlapRatio = (candidate) => {
  const matched = new Set(candidate?.matched_skills || []).size;
  const missing = new Set([
    ...(candidate?.missing_skills || []),
    ...(candidate?.missing_critical || []),
  ]).size;
  return matched + missing > 0 ? matched / (matched + missing) : 0;
};

export const effectiveThreshold = (candidates, threshold) => {
  if (threshold === null || candidates.length === 0) return null;
  // Calibrated target is capped per vacancy to retain the first ranked result.
  return Math.min(threshold, overlapRatio(candidates[0]));
};

export const filterCandidates = (candidates, threshold) => {
  const value = effectiveThreshold(candidates, threshold);
  return value === null ? candidates : candidates.filter(c => overlapRatio(c) >= value);
};
