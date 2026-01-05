import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { DiagramTeachingProvider } from "@/context/DiagramTeachingContext";

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <DiagramTeachingProvider>
      <App />
    </DiagramTeachingProvider>
  </React.StrictMode>,
);
