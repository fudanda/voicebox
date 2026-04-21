/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $EffectConfig = {
    description: `A single effect in an effects chain.`,
    properties: {
        type: {
            type: 'string',
            isRequired: true,
        },
        enabled: {
            type: 'boolean',
        },
        params: {
            type: 'dictionary',
            contains: {
                properties: {
                },
            },
        },
    },
} as const;
