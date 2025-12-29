import axios, { AxiosInstance, AxiosRequestConfig } from "axios";
import useSessionStore from "../store/sessionStore";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const WS_BASE_URL = API_BASE_URL.replace("http://", "ws://").replace("https://", "wss://");

interface JobUpdateMessage {
    type: "job_update";
    job_id: string;
    status: string;
    progress: number;
    error?: string;
    result?: {
        pptx_url?: string;
        pdf_url?: string;
        video_url?: string;
    };
}

class ApiClient {
    private client: AxiosInstance;
    private ws: WebSocket | null = null;
    private wsReconnectTimeout: NodeJS.Timeout | null = null;
    private jobUpdateCallbacks: Map<string, (data: JobUpdateMessage) => void> = new Map();

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

    // WebSocket methods for real-time updates
    connectWebSocket(sessionId: string): void {
        console.log("[WebSocket] Attempting to connect for session:", sessionId);
        
        if (this.ws?.readyState === WebSocket.OPEN) {
            console.log("[WebSocket] Already connected");
            return;
        }

        try {
            this.ws = new WebSocket(`${WS_BASE_URL}/api/ws/${sessionId}`);

            this.ws.onopen = () => {
                console.log("[WebSocket] Connected successfully");
                // Clear any reconnect timeout
                if (this.wsReconnectTimeout) {
                    clearTimeout(this.wsReconnectTimeout);
                    this.wsReconnectTimeout = null;
                }
                // Send ping every 30s to keep alive
                const pingInterval = setInterval(() => {
                    if (this.ws?.readyState === WebSocket.OPEN) {
                        this.ws.send("ping");
                    } else {
                        clearInterval(pingInterval);
                    }
                }, 30000);
            };

            this.ws.onmessage = (event) => {
                try {
                    const data: JobUpdateMessage = JSON.parse(event.data);
                    console.log("[WebSocket] Received message:", data);
                    
                    if (data.type === "job_update") {
                        const callback = this.jobUpdateCallbacks.get(data.job_id);
                        if (callback) {
                            callback(data);
                        }
                    }
                } catch (error) {
                    // Ignore non-JSON messages (like pong)
                    console.debug("[WebSocket] Non-JSON message:", event.data);
                }
            };

            this.ws.onerror = (error) => {
                console.error("[WebSocket] Error:", error);
            };

            this.ws.onclose = () => {
                console.log("[WebSocket] Connection closed, will attempt to reconnect...");
                // Attempt to reconnect after 2 seconds
                this.wsReconnectTimeout = setTimeout(() => {
                    console.log("[WebSocket] Reconnecting...");
                    this.connectWebSocket(sessionId);
                }, 2000);
            };
        } catch (error) {
            console.error("[WebSocket] Failed to connect:", error);
            // Fall back to polling
        }
    }

    disconnectWebSocket(): void {
        console.log("[WebSocket] Disconnecting");
        if (this.wsReconnectTimeout) {
            clearTimeout(this.wsReconnectTimeout);
            this.wsReconnectTimeout = null;
        }
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.jobUpdateCallbacks.clear();
    }

    subscribeToJobUpdates(
        jobId: string,
        callback: (data: JobUpdateMessage) => void
    ): () => void {
        console.log("[WebSocket] Subscribing to job updates:", jobId);
        this.jobUpdateCallbacks.set(jobId, callback);
        
        // Return unsubscribe function
        return () => {
            console.log("[WebSocket] Unsubscribing from job updates:", jobId);
            this.jobUpdateCallbacks.delete(jobId);
        };
    }

    async pollJobWithWebSocket(
        jobId: string,
        onProgress?: (progress: number) => void
    ): Promise<{
        pptx_url?: string;
        pdf_url?: string;
        video_url?: string;
    }> {
        return new Promise((resolve, reject) => {
            let resolved = false;
            let pollFallbackTimeout: NodeJS.Timeout | null = null;

            // Subscribe to WebSocket updates
            const unsubscribe = this.subscribeToJobUpdates(jobId, (data) => {
                if (resolved) return;

                console.log("[WebSocket] Job update received:", data);

                if (onProgress && data.progress !== undefined) {
                    onProgress(data.progress);
                }

                if (data.status === "completed") {
                    resolved = true;
                    unsubscribe();
                    if (pollFallbackTimeout) clearTimeout(pollFallbackTimeout);
                    resolve(data.result || {});
                }

                if (data.status === "failed") {
                    resolved = true;
                    unsubscribe();
                    if (pollFallbackTimeout) clearTimeout(pollFallbackTimeout);
                    reject(new Error(data.error || "Job failed"));
                }
            });

            // Fallback to polling if WebSocket not connected after 1 second
            pollFallbackTimeout = setTimeout(() => {
                if (!resolved && this.ws?.readyState !== WebSocket.OPEN) {
                    console.log("[WebSocket] Not connected, falling back to polling");
                    unsubscribe();
                    this.pollJobUntilComplete(jobId, onProgress)
                        .then(resolve)
                        .catch(reject);
                }
            }, 1000);

            // Also do an initial status check to handle race conditions
            this.getJobStatus(jobId)
                .then(({ job, result }) => {
                    if (resolved) return;
                    
                    if (onProgress) onProgress(job.progress);
                    
                    if (job.status === "completed") {
                        resolved = true;
                        unsubscribe();
                        if (pollFallbackTimeout) clearTimeout(pollFallbackTimeout);
                        resolve(result || {});
                    } else if (job.status === "failed") {
                        resolved = true;
                        unsubscribe();
                        if (pollFallbackTimeout) clearTimeout(pollFallbackTimeout);
                        reject(new Error(job.error || "Job failed"));
                    }
                })
                .catch((error) => {
                    if (!resolved) {
                        console.error("[WebSocket] Initial status check failed:", error);
                    }
                });
        });
    }
}

export const apiClient = new ApiClient();
export default apiClient;
