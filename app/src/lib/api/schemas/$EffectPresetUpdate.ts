/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $EffectPresetUpdate = {
    description: `Request model for updating an effect preset.`,
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
        description: {
            type: 'any-of',
            contains: [{
                type: 'string',
            }, {
                type: 'null',
            }],
        },
        effects_chain: {
            type: 'any-of',
            contains: [{
                type: 'array',
                contains: {
                    type: 'EffectConfig',
                },
            }, {
                type: 'null',
            }],
        },
    },
} as const;
