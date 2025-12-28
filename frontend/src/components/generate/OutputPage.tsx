import { useFileStore, useSessionStore } from "../../store";
import apiClient from "../../api/client";

export default function OutputPage() {
    const [slidesGenerated, videoGenerated] = useFileStore((state) => [
        state.slidesGenerated,
        state.videoGenerated,
    ]);

    const pptxUrl = apiClient.getFileUrl("presentation.pptx");
    const pdfUrl = apiClient.getFileUrl("presentation.pdf");
    const videoUrl = apiClient.getFileUrl("video.mp4");

    return (
        <div className="byteContainer w-full md:w-auto flex flex-col items-center mx-auto py-12 px-8 md:px-20 bg-translucent-normal border border-[#ffffff1c] rounded-lg space-y-10">
            <h1 className="text-2xl text-center font-medium">Output</h1>

            <div className="flex flex-col space-y-10">
                {slidesGenerated && (
                    <div className="space-y-2">
                        <p className="text-md">Slides</p>
                        <div className="flex gap-12">
                            <a
                                className="px-4 py-2 flex gap-4 border border-[#ffffff2c] rounded-lg"
                                href={pptxUrl}
                                target="_blank"
                            >
                                <span>PPTX</span>
                                <svg className="w-6 h-6">
                                    <use xlinkHref="#new-page"></use>
                                </svg>
                            </a>
                            <a
                                className="px-4 py-2 flex gap-4 border border-[#ffffff2c] rounded-lg"
                                href={pdfUrl}
                                target="_blank"
                            >
                                <span>PDF</span>
                                <svg className="w-6 h-6">
                                    <use xlinkHref="#new-page"></use>
                                </svg>
                            </a>
                        </div>
                    </div>
                )}
                {videoGenerated && (
                    <div className="space-y-2">
                        <p className="text-md">Video</p>
                        <div className="flex space-x-6">
                            <a
                                className="px-4 py-2 flex gap-4 border border-[#ffffff2c] rounded-lg"
                                href={videoUrl}
                                target="_blank"
                            >
                                <span>mp4</span>
                                <svg className="w-6 h-6">
                                    <use xlinkHref="#new-page"></use>
                                </svg>
                            </a>
                        </div>
                    </div>
                )}

                {!slidesGenerated && !videoGenerated && (
                    <div className="space-y-2">
                        <p className="text-md">No content generated!</p>
                    </div>
                )}
            </div>
        </div>
    );
}
