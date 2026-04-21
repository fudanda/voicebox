/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $StoryItemTrim = {
    description: `Request model for trimming a story item.`,
    properties: {
        trim_start_ms: {
            type: 'number',
            isRequired: true,
        },
        trim_end_ms: {
            type: 'number',
            isRequired: true,
        },
    },
} as const;
