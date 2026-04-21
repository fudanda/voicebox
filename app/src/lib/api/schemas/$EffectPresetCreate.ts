/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $EffectPresetCreate = {
    description: `Request model for creating an effect preset.`,
    properties: {
        name: {
            type: 'string',
            isRequired: true,
            maxLength: 100,
            minLength: 1,
        },
        description: {
            type: 'any-of',
            contains: [{
                type: 'string',
                maxLength: 500,
            }, {
                type: 'null',
            }],
        },
        effects_chain: {
            type: 'array',
            contains: {
                type: 'EffectConfig',
            },
            isRequired: true,
        },
    },
} as const;
