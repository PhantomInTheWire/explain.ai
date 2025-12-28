import { useState, useEffect } from "react";
import apiClient from "../../api/client";
import { useFileStore, useProgressStore, useSessionStore } from "../../store";

export default function GeneratePage() {
    const [fileUploaded, setFileUploaded] = useState(false);
    const [loading, setLoading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [statusMessage, setStatusMessage] = useState("");

    const [isValidFile, file, filename, setSlidesGenerated, setVideoGenerated] =
        useFileStore((state) => [
            state.validFile,
            state.file,
            state.fileName,
            state.setSlidesGenerated,
            state.setVideoGenerated,
        ]);

    const [outputForms, selectedTheme, setCurrentState] = useProgressStore(
        (state) => [state.outputs, state.currentTheme, state.setCurrentState]
    );

    const sessionId = useSessionStore((state) => state.sessionId);
    const createSession = useSessionStore((state) => state.createSession);

    useEffect(() => {
        createSession();
    }, [createSession]);

    const choices = [
        { title: "File", isList: false, state: filename, section: "Upload" },
        { title: "Output", isList: true, state: outputForms.join(", "), section: "Select" },
        { title: "Theme", isList: false, state: selectedTheme, section: "Customize" },
    ];

    const ensureFileUploaded = async () => {
        if (fileUploaded || !file) return;

        setStatusMessage("Uploading PDF...");
        setProgress(5);

        try {
            const { job_id } = await apiClient.uploadPdf(file);
            await apiClient.pollJobUntilComplete(job_id, (p) => setProgress(Math.min(p, 20)));
            setFileUploaded(true);
            setProgress(20);
        } catch (error) {
            console.error("Error uploading file:", error);
            throw error;
        }
    };

    const handleGenerate = async () => {
        setLoading(true);
        setProgress(0);

        try {
            await ensureFileUploaded();

            if (outputForms.includes("Slides") || outputForms.length === 2) {
                setStatusMessage("Generating presentation...");
                const { job_id } = await apiClient.generatePresentation(selectedTheme);
                await apiClient.pollJobUntilComplete(job_id, (p) =>
                    setProgress(20 + Math.min(p * 0.4, 40))
                );
                setSlidesGenerated(true);
                setProgress(60);
            }

            if (outputForms.includes("Video") || outputForms.length === 2) {
                setStatusMessage("Generating video...");
                const { job_id } = await apiClient.generateVideo();
                await apiClient.pollJobUntilComplete(job_id, (p) =>
                    setProgress(60 + Math.min(p * 0.4, 40))
                );
                setVideoGenerated(true);
                setProgress(100);
            }

            setStatusMessage("Complete!");
            setCurrentState("Output");
        } catch (error) {
            console.error("Error generating content:", error);
            setStatusMessage("Error occurred. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="byteContainer flex flex-col items-center mx-auto py-12 px-8 md:px-20 bg-translucent-normal border border-[#ffffff1c] rounded-lg space-y-10">
            <h1 className="text-2xl font-medium">Generate</h1>

            {sessionId && (
                <p className="text-xs text-secondary">Session: {sessionId.slice(0, 8)}...</p>
            )}

            <div className="space-y-2">
                <div className="flex flex-col space-y-6">
                    {choices.map((option, index) => (
                        <div className="flex flex-col space-y-2" key={index}>
                            <p className="text-md">{option.title}</p>
                            <button
                                className="flex items-center gap-4 px-4 py-2 rounded-lg border-2 border-[#ffffff1c] text-left [&:hover>svg]:opacity-100"
                                onClick={() => setCurrentState(option.section)}
                            >
                                <p className="w-full min-w-40 md:min-w-60 text-left text-secondary text-xs">
                                    {option.state}
                                </p>
                                <svg className="w-6 h-6 opacity-0">
                                    <use xlinkHref="#edit"></use>
                                </svg>
                            </button>
                        </div>
                    ))}
                </div>
            </div>

            {loading && (
                <div className="w-full">
                    <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                        <div
                            className="h-full bg-gradient-to-r from-purple-500 to-pink-500 transition-all duration-300"
                            style={{ width: `${progress}%` }}
                        />
                    </div>
                    <p className="text-sm text-secondary mt-2">{statusMessage}</p>
                </div>
            )}

            {isValidFile ? (
                <button
                    className="text-xl font-semibold px-[.1rem] py-[.1rem] bgGradient rounded-lg"
                    onClick={handleGenerate}
                    disabled={loading}
                >
                    <p className="w-full px-3 py-1 bg-offBlack rounded-lg">
                        <span className="textGradient">
                            {loading ? "Generating..." : "Generate"}
                        </span>
                    </p>
                </button>
            ) : (
                <button
                    disabled
                    className="text-xl font-semibold px-[.1rem] py-[.1rem] bg-secondary rounded-lg"
                >
                    <p className="w-full px-3 py-1 bg-offBlack rounded-lg">
                        <span className="text-secondary">Generate</span>
                    </p>
                </button>
            )}
        </div>
    );
}
