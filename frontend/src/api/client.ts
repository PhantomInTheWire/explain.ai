import axios, { AxiosInstance, AxiosRequestConfig } from "axios";
import useSessionStore from "../store/sessionStore";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

class ApiClient {
    private client: AxiosInstance;

    constructor() {
        this.client = axios.create({
            baseURL: API_BASE_URL,
            headers: {
                "Content-Type": "application/json",
            },
        });

        this.client.interceptors.request.use((config) => {
            const sessionId = useSessionStore.getState().sessionId;
            if (sessionId) {
                config.headers["X-Session-ID"] = sessionId;
            }
            return config;
        });

        this.client.interceptors.response.use(
            (response) => response,
            async (error) => {
                if (error.response?.status === 401) {
                    useSessionStore.getState().clearSession();
                    await useSessionStore.getState().createSession();
                }
                return Promise.reject(error);
            }
        );
    }

    async ensureSession(): Promise<string> {
        return useSessionStore.getState().createSession();
    }

    async uploadPdf(file: File): Promise<{ job_id: string }> {
        await this.ensureSession();
        const formData = new FormData();
        formData.append("file", file);
        const response = await this.client.post("/api/upload_pdf/", formData, {
            headers: { "Content-Type": "multipart/form-data" },
        });
        return response.data;
    }

    async generatePresentation(theme: string): Promise<{ job_id: string }> {
        await this.ensureSession();
        const response = await this.client.post("/api/get_presentation/", { theme });
        return response.data;
    }

    async generateVideo(): Promise<{ job_id: string }> {
        await this.ensureSession();
        const response = await this.client.post("/api/generate_video/", {});
        return response.data;
    }

    async getJobStatus(jobId: string): Promise<{
        job: {
            status: string;
            progress: number;
            error?: string;
        };
        result?: {
            pptx_url?: string;
            pdf_url?: string;
            video_url?: string;
        };
    }> {
        await this.ensureSession();
        const response = await this.client.get(`/api/jobs/${jobId}`);
        return response.data;
    }

    async pollJobUntilComplete(
        jobId: string,
        onProgress?: (progress: number) => void,
        intervalMs: number = 2000
    ): Promise<{
        pptx_url?: string;
        pdf_url?: string;
        video_url?: string;
    }> {
        return new Promise((resolve, reject) => {
            const poll = async () => {
                try {
                    const { job, result } = await this.getJobStatus(jobId);

                    if (onProgress) {
                        onProgress(job.progress);
                    }

                    if (job.status === "completed") {
                        resolve(result || {});
                        return;
                    }

                    if (job.status === "failed") {
                        reject(new Error(job.error || "Job failed"));
                        return;
                    }

                    setTimeout(poll, intervalMs);
                } catch (error) {
                    reject(error);
                }
            };
            poll();
        });
    }

    getFileUrl(filename: string): string {
        const sessionId = useSessionStore.getState().sessionId;
        return `${API_BASE_URL}/api/sessions/${sessionId}/files/${filename}`;
    }
}

export const apiClient = new ApiClient();
export default apiClient;
