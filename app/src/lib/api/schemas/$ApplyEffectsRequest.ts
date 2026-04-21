/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ApplyEffectsRequest = {
    description: `Request to apply effects to an existing generation.`,
    properties: {
        effects_chain: {
            type: 'array',
            contains: {
                type: 'EffectConfig',
            },
            isRequired: true,
        },
        source_version_id: {
            type: 'any-of',
            description: `Version to use as source audio (defaults to clean/original)`,
            contains: [{
                type: 'string',
            }, {
                type: 'null',
            }],
        },
        label: {
            type: 'any-of',
            description: `Label for this version (auto-generated if omitted)`,
            contains: [{
                type: 'string',
                maxLength: 100,
            }, {
                type: 'null',
            }],
        },
        set_as_default: {
            type: 'boolean',
            description: `Set this version as the default`,
        },
    },
} as const;
