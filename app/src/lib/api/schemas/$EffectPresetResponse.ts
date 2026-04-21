/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $EffectPresetResponse = {
    description: `Response model for effect preset.`,
    properties: {
        id: {
            type: 'string',
            isRequired: true,
        },
        name: {
            type: 'string',
            isRequired: true,
        },
        description: {
            type: 'any-of',
            contains: [{
                type: 'string',
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
        is_builtin: {
            type: 'boolean',
        },
        created_at: {
            type: 'string',
            isRequired: true,
            format: 'date-time',
        },
    },
} as const;
