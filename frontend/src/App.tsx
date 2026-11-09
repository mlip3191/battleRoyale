import { Route, Routes } from "react-router-dom";
import Home from "./pages/Home.tsx";

// Top-level routes; Battle and Results pages are added by later tasks.
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
    </Routes>
  );
}
