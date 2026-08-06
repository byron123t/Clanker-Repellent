// Synthetic implementation sketch for issue-triage fixtures.
export function renderCard(title, description) {
  if (!description) return "";
  return `<article><h2>${title}</h2><p>${description}</p></article>`;
}
