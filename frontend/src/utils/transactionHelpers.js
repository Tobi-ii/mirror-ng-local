// src/utils/transactionHelpers.js

const ML_GROUPS = [
  { pattern: /airtime|mtn|\bglo\b|airtel|9mobile/i, name: 'Airtime Purchase', category: 'Data & Airtime' },
  { pattern: /data purchase|data plan|internet/i, name: 'Data Purchase', category: 'Data & Airtime' },
  // POS purchases are Shopping (explicit rule)
  { pattern: /pos purchase|pos transaction|point of sale|purchase at/i, name: 'Shopping', category: 'Shopping' },
  // Bank Transfer patterns (removed \bpos\b since POS is Shopping)
  { pattern: /transfer to|sent to|payment to|nip transfer|transfer from|onebank transfer|\batm\b|withdrawal/i, name: 'Bank Transfer', category: 'Transfer' },
  { pattern: /ebill|electric|ikeja|eko disco|abuja disco/i, name: 'Electricity Bill', category: 'Utilities' },
  { pattern: /vat|value added tax/i, name: 'VAT Charge', category: 'Utilities' },
  { pattern: /card maintenance|card fee/i, name: 'Card Fee', category: 'Utilities' },
  { pattern: /food|restaurant|cafe|eatery|mcdonald|kfc|chicken|rice/i, name: 'Food Purchase', category: 'Food' },
  { pattern: /uber|bolt|taxi|transport/i, name: 'Transport', category: 'Transport' },
  { pattern: /salary|wage|payment from/i, name: 'Salary', category: 'Salary' },
];

export function getMLSuggestion(narration) {
  if (!narration) return null;
  for (const group of ML_GROUPS) {
    if (group.pattern.test(narration)) {
      return { display_name: group.name, category: group.category };
    }
  }
  return null;
}

export function groupSimilarTransactions(transactions) {
  if (!transactions || transactions.length === 0) return { groups: {}, ungrouped: [] };
  const groups = {};
  const ungrouped = [];
  for (const tx of transactions) {
    const suggestion = getMLSuggestion(tx.original_narration || tx.narration);
    if (suggestion) {
      const key = suggestion.display_name;
      if (!groups[key]) {
        groups[key] = { display_name: suggestion.display_name, category: suggestion.category, transactions: [] };
      }
      groups[key].transactions.push(tx);
    } else if (tx.category && tx.category !== 'General') {
      const CATEGORY_MAP = {
        'Transfer': 'Bank Transfer',
        'Utilities': 'Bills & Utilities',
        'Shopping': 'Shopping',
        'Income': 'Income'
      };
      const groupName = CATEGORY_MAP[tx.category] || tx.category;
      if (!groups[groupName]) {
        groups[groupName] = { display_name: groupName, category: tx.category, transactions: [] };
      }
      groups[groupName].transactions.push(tx);
    } else {
      ungrouped.push(tx);
    }
  }
  return { groups, ungrouped };
}