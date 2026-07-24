import { createContext, useContext, useState } from 'react';

const BlurContext = createContext();

export function BlurProvider({ children }) {
  const [disableBlur, setDisableBlur] = useState(false);

  return (
    <BlurContext.Provider value={{ disableBlur, setDisableBlur }}>
      {children}
    </BlurContext.Provider>
  );
}

export function useBlur() {
  const context = useContext(BlurContext);
  if (!context) {
    throw new Error('useBlur must be used within a BlurProvider');
  }
  return context;
}