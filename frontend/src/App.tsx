import { Route, Routes } from "react-router-dom";
import { About, Generate, Header, Home } from "./components";
import { SystemIcons } from "./icons";
import "./App.css";

export default function App() {
    return (
        <div className="min-w-full min-h-screen container">
            <SystemIcons />
            <Header />

            <main className="w-full min-h-screen flex flex-col md:flex-row gap-8 pt-24 pb-6 px-2">
                <Routes>
                    <Route path="/" element={<Home />} />
                    <Route path="/generate" element={<Generate />} />
                    <Route path="/about" element={<About />} />
                </Routes>
            </main>
        </div>
    );
}
