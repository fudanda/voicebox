/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $TranscriptionSubtitlesResponse = {
    description: `Response model for transcription with subtitle segments.`,
    properties: {
        text: {
            type: 'string',
            isRequired: true,
        },
        duration: {
            type: 'number',
            isRequired: true,
        },
        segments: {
            type: 'array',
            contains: {
                type: 'TranscriptionSegment',
            },
            isRequired: true,
        },
    },
} as const;
