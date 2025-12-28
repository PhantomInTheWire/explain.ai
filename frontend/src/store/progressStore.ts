import { create } from "zustand";

interface progressStoreInterface {
    currentState: string;
    outputs: string[];
    currentTheme: string;
    setCurrentState: (newState: string) => void;
    updateOutputs: (newOutputs: string[]) => void;
    setCurrentTheme: (newTheme: string) => void;
    toggleOutputChoice: (output: string) => void;
}

const useProgressStore = create<progressStoreInterface>((set) => ({
    currentState: "Upload",
    outputs: ["Slides"],
    currentTheme: "Auto",
    setCurrentState: (newState: string) =>
        set(() => ({
            currentState: newState,
        })),
    updateOutputs: (newOutputs: string[]) =>
        set(() => ({
            outputs: newOutputs,
        })),
    setCurrentTheme: (newTheme: string) =>
        set(() => ({ currentTheme: newTheme })),
    toggleOutputChoice: (output: string) =>
        set((state) => {
            let choice = state.outputs.includes(output);
            if (choice) {
                if (state.outputs.length == 1)
                    return { outputs: state.outputs };
                return {
                    outputs: state.outputs.filter((op) => op !== output),
                };
            }
            return { outputs: [...state.outputs, output] };
        }),
}));

export default useProgressStore;
