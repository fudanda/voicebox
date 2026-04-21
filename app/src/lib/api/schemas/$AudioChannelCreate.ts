/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $AudioChannelCreate = {
    description: `Request model for creating an audio channel.`,
    properties: {
        name: {
            type: 'string',
            isRequired: true,
            maxLength: 100,
            minLength: 1,
        },
        device_ids: {
            type: 'array',
            contains: {
                type: 'string',
            },
        },
    },
} as const;
