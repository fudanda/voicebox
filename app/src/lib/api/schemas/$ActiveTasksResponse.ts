/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ActiveTasksResponse = {
    description: `Response model for active tasks.`,
    properties: {
        downloads: {
            type: 'array',
            contains: {
                type: 'ActiveDownloadTask',
            },
            isRequired: true,
        },
        generations: {
            type: 'array',
            contains: {
                type: 'ActiveGenerationTask',
            },
            isRequired: true,
        },
    },
} as const;
