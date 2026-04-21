/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ActiveGenerationTask = {
    description: `Response model for active generation task.`,
    properties: {
        task_id: {
            type: 'string',
            isRequired: true,
        },
        profile_id: {
            type: 'string',
            isRequired: true,
        },
        text_preview: {
            type: 'string',
            isRequired: true,
        },
        started_at: {
            type: 'string',
            isRequired: true,
            format: 'date-time',
        },
    },
} as const;
