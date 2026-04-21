/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $AudioChannelResponse = {
    description: `Response model for audio channel.`,
    properties: {
        id: {
            type: 'string',
            isRequired: true,
        },
        name: {
            type: 'string',
            isRequired: true,
        },
        is_default: {
            type: 'boolean',
            isRequired: true,
        },
        device_ids: {
            type: 'array',
            contains: {
                type: 'string',
            },
            isRequired: true,
        },
        created_at: {
            type: 'string',
            isRequired: true,
            format: 'date-time',
        },
    },
} as const;
