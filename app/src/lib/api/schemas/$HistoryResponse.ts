/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $HistoryResponse = {
    description: `Response model for history entry (includes profile name).`,
    properties: {
        id: {
            type: 'string',
            isRequired: true,
        },
        profile_id: {
            type: 'string',
            isRequired: true,
        },
        profile_name: {
            type: 'string',
            isRequired: true,
        },
        text: {
            type: 'string',
            isRequired: true,
        },
        language: {
            type: 'string',
            isRequired: true,
        },
        audio_path: {
            type: 'any-of',
            contains: [{
                type: 'string',
            }, {
                type: 'null',
            }],
        },
        duration: {
            type: 'any-of',
            contains: [{
                type: 'number',
            }, {
                type: 'null',
            }],
        },
        seed: {
            type: 'any-of',
            contains: [{
                type: 'number',
            }, {
                type: 'null',
            }],
        },
        instruct: {
            type: 'any-of',
            contains: [{
                type: 'string',
            }, {
                type: 'null',
            }],
        },
        engine: {
            type: 'any-of',
            contains: [{
                type: 'string',
            }, {
                type: 'null',
            }],
        },
        model_size: {
            type: 'any-of',
            contains: [{
                type: 'string',
            }, {
                type: 'null',
            }],
        },
        status: {
            type: 'string',
        },
        error: {
            type: 'any-of',
            contains: [{
                type: 'string',
            }, {
                type: 'null',
            }],
        },
        is_favorited: {
            type: 'boolean',
        },
        created_at: {
            type: 'string',
            isRequired: true,
            format: 'date-time',
        },
        versions: {
            type: 'any-of',
            contains: [{
                type: 'array',
                contains: {
                    type: 'GenerationVersionResponse',
                },
            }, {
                type: 'null',
            }],
        },
        active_version_id: {
            type: 'any-of',
            contains: [{
                type: 'string',
            }, {
                type: 'null',
            }],
        },
    },
} as const;
