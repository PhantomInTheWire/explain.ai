import React, { useState } from "react";
import {
    UploadIcon,
    SelectIcon,
    CustomizeIcon,
    GenerateIcon,
} from "../../icons";
import ProgressSection from "./ProgressSection";
import { useProgressStore } from "../../store";
import UploadPage from "./UploadPage";
import SelectPage from "./SelectPage";
import CustomizePage from "./CustomizePage";
import GeneratePage from "./GeneratePage";
import OutputPage from "./OutputPage";
const states = [
    { name: "Upload", page: UploadPage },
    { name: "Select", page: SelectPage },
    { name: "Customize", page: CustomizePage },
    { name: "Generate", page: GeneratePage },
    { name: "Output", page: OutputPage },
];

export default function Generate() {
    const [currentState] = useProgressStore((state) => [state.currentState]);
    return (
        <>
            <ProgressSection />
            <div className="flex-grow flex flex-col pt-8 md:pt-16">
                {states.map((state, index) => (
                    <React.Fragment key={index}>
                        {currentState === state.name && <state.page />}
                    </React.Fragment>
                ))}
            </div>
        </>
    );
}
