/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $AudioChannelUpdate = {
    description: `Request model for updating an audio channel.`,
    properties: {
        name: {
            type: 'any-of',
            contains: [{
                type: 'string',
                maxLength: 100,
                minLength: 1,
            }, {
                type: 'null',
            }],
        },
        device_ids: {
            type: 'any-of',
            contains: [{
                type: 'array',
                contains: {
                    type: 'string',
                },
            }, {
                type: 'null',
            }],
        },
    },
} as const;
