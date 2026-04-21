/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $FilesystemHealthResponse = {
    description: `Response model for filesystem health check.`,
    properties: {
        healthy: {
            type: 'boolean',
            isRequired: true,
        },
        disk_free_mb: {
            type: 'any-of',
            contains: [{
                type: 'number',
            }, {
                type: 'null',
            }],
        },
        disk_total_mb: {
            type: 'any-of',
            contains: [{
                type: 'number',
            }, {
                type: 'null',
            }],
        },
        directories: {
            type: 'array',
            contains: {
                type: 'DirectoryCheck',
            },
            isRequired: true,
        },
    },
} as const;
