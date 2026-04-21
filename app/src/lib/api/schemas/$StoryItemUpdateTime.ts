/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $StoryItemUpdateTime = {
    description: `Request model for updating a story item's timecode.`,
    properties: {
        generation_id: {
            type: 'string',
            isRequired: true,
        },
        start_time_ms: {
            type: 'number',
            isRequired: true,
        },
    },
} as const;
