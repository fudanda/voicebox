/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $TranscriptionSegment = {
    description: `Segment-level transcription timestamp.`,
    properties: {
        index: {
            type: 'number',
            isRequired: true,
        },
        start: {
            type: 'number',
            isRequired: true,
        },
        end: {
            type: 'number',
            isRequired: true,
        },
        text: {
            type: 'string',
            isRequired: true,
        },
    },
} as const;
