import { useMemo } from 'react';

export const useMirror = (transactions, startingBalance) => {
  const stats = useMemo(() => {
    return transactions.reduce(
      (acc, tx) => {
        const amt = Number(tx.amount);
        // Logic: Credits add to balance, Debits subtract
        if (tx.tx_type === 'credit') {
          acc.totalIn += amt;
        } else if (tx.tx_type === 'debit') {
          acc.totalOut += amt;
        }
        return acc;
      },
      { totalIn: 0, totalOut: 0 }
    );
  }, [transactions]);

  const netPerformance = stats.totalIn - stats.totalOut;
  const aggregateLiquidity = Number(startingBalance) + netPerformance;

  return {
    aggregateLiquidity,
    totalIn: stats.totalIn,
    totalOut: stats.totalOut,
    netPerformance,
  };
};