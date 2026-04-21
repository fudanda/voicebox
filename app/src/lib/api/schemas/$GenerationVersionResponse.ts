/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $GenerationVersionResponse = {
    description: `Response model for a generation version.`,
    properties: {
        id: {
            type: 'string',
            isRequired: true,
        },
        generation_id: {
            type: 'string',
            isRequired: true,
        },
        label: {
            type: 'string',
            isRequired: true,
        },
        audio_path: {
            type: 'string',
            isRequired: true,
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
        source_version_id: {
            type: 'any-of',
            contains: [{
                type: 'string',
            }, {
                type: 'null',
            }],
        },
        is_default: {
            type: 'boolean',
            isRequired: true,
        },
        created_at: {
            type: 'string',
            isRequired: true,
            format: 'date-time',
        },
    },
} as const;
