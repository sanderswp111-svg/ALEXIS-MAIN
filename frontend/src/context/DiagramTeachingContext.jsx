import React, { createContext, useContext, useState, useCallback } from "react";

const DiagramTeachingContext = createContext(null);

export const DiagramTeachingProvider = ({ children }) => {
  const [diagramTeachingEnabled, setDiagramTeachingEnabled] = useState(false);
  const [responseMode, setResponseMode] = useState("EXPLANATION"); // "EXPLANATION" | "DIAGRAM_TEACHING" | "AUTHORITY" (future)

  const enableDiagramTeaching = useCallback(() => {
    setDiagramTeachingEnabled(true);
    setResponseMode("DIAGRAM_TEACHING");
  }, []);

  const disableDiagramTeaching = useCallback(() => {
    setDiagramTeachingEnabled(false);
    setResponseMode("EXPLANATION");
  }, []);

  return (
    <DiagramTeachingContext.Provider
      value={{
        diagramTeachingEnabled,
        responseMode,
        setResponseMode,
        enableDiagramTeaching,
        disableDiagramTeaching,
      }}
    >
      {children}
    </DiagramTeachingContext.Provider>
  );
};

export const useDiagramTeaching = () => {
  const ctx = useContext(DiagramTeachingContext);
  if (!ctx) {
    throw new Error("useDiagramTeaching must be used within a DiagramTeachingProvider");
  }
  return ctx;
};
