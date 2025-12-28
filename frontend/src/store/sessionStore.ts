import { create } from "zustand";
import { persist } from "zustand/middleware";

interface SessionState {
    sessionId: string | null;
    isLoading: boolean;
    error: string | null;
    createSession: () => Promise<string>;
    clearSession: () => void;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const useSessionStore = create<SessionState>()(
    persist(
        (set, get) => ({
            sessionId: null,
            isLoading: false,
            error: null,

            createSession: async () => {
                const existing = get().sessionId;
                if (existing) {
                    try {
                        const response = await fetch(
                            `${API_BASE_URL}/api/sessions/${existing}`
                        );
                        if (response.ok) {
                            return existing;
                        }
                    } catch {
                        // Session invalid, create new one
                    }
                }

                set({ isLoading: true, error: null });
                try {
                    const response = await fetch(`${API_BASE_URL}/api/sessions`, {
                        method: "POST",
                    });
                    if (!response.ok) {
                        throw new Error("Failed to create session");
                    }
                    const data = await response.json();
                    set({ sessionId: data.session_id, isLoading: false });
                    return data.session_id;
                } catch (error) {
                    set({
                        error: error instanceof Error ? error.message : "Unknown error",
                        isLoading: false,
                    });
                    throw error;
                }
            },

            clearSession: () => {
                set({ sessionId: null, error: null });
            },
        }),
        {
            name: "vedanta-session",
            partialize: (state) => ({ sessionId: state.sessionId }),
        }
    )
);

export default useSessionStore;
