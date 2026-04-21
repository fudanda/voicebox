/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ProfileEffectsUpdate = {
    description: `Request to update the default effects chain on a profile.`,
    properties: {
        effects_chain: {
            type: 'any-of',
            description: `Effects chain (null to remove)`,
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
