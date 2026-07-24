import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';

const BalanceContext = createContext();

export function BalanceProvider({ children, userId }) {
  const [balances, setBalances] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [totalBalance, setTotalBalance] = useState(0);
  const [isLoading, setIsLoading] = useState(true);

  const refreshData = useCallback(async () => {
    if (!userId) return;
    setIsLoading(true);
    try {
      const [balRes, txRes] = await Promise.all([
        api.getBalances(userId),
        api.getTransactions(userId, { limit: 300 })
      ]);

      const accounts = balRes?.balances || [];
      setBalances(accounts);
      setTransactions(txRes?.transactions || []);
      
      const total = accounts.reduce((sum, acc) => sum + (acc.balance || 0), 0);
      setTotalBalance(total);
    } catch (error) {
      console.error('Mirror Vault Error:', error);
    } finally {
      setIsLoading(false);
    }
  }, [userId]);

  const deleteBalance = async (bank, last4) => {
    try {
      await api.deleteBalance(userId, bank, last4);
      await refreshData(); 
    } catch (error) {
      console.error('Mirror Vault Error (Delete):', error);
      throw error;
    }
  };

  const adjustBalance = async (bank, last4, amount) => {
    try {
      await api.adjustBalance(userId, bank, last4, amount, 'user_manual_adjustment');
      await refreshData();
    } catch (error) {
      console.error('Mirror Vault Error (Adjust):', error);
    }
  };

  useEffect(() => {
    refreshData();
  }, [refreshData]);

  return (
    <BalanceContext.Provider 
      value={{ 
        balances, 
        transactions, 
        totalBalance, 
        isLoading, 
        refreshData, 
        deleteBalance,
        adjustBalance 
      }}
    >
      {children}
    </BalanceContext.Provider>
  );
}

export const useBalances = () => {
  const context = useContext(BalanceContext);
  if (!context) throw new Error('useBalances must be used within a BalanceProvider');
  return context;
};