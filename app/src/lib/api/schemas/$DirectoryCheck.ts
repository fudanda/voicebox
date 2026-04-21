/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $DirectoryCheck = {
    description: `Health status for a single directory.`,
    properties: {
        path: {
            type: 'string',
            isRequired: true,
        },
        exists: {
            type: 'boolean',
            isRequired: true,
        },
        writable: {
            type: 'boolean',
            isRequired: true,
        },
        error: {
            type: 'any-of',
            contains: [{
                type: 'string',
            }, {
                type: 'null',
            }],
        },
    },
} as const;
