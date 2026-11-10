import { Route, Routes } from "react-router-dom";
import { Header } from "./components/Broadcast.tsx";
import Battle from "./pages/Battle.tsx";
import Home from "./pages/Home.tsx";
import NotFound from "./pages/NotFound.tsx";
import Results from "./pages/Results.tsx";

// The broadcast frame and every top-level route.
export default function App() {
  return (
    <>
      <Header />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/battle/:id" element={<Battle />} />
        <Route path="/battle/:id/results" element={<Results />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </>
  );
}
