/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $StoryItemDetail = {
    description: `Detail model for story item with generation info.`,
    properties: {
        id: {
            type: 'string',
            isRequired: true,
        },
        story_id: {
            type: 'string',
            isRequired: true,
        },
        generation_id: {
            type: 'string',
            isRequired: true,
        },
        version_id: {
            type: 'any-of',
            contains: [{
                type: 'string',
            }, {
                type: 'null',
            }],
        },
        start_time_ms: {
            type: 'number',
            isRequired: true,
        },
        track: {
            type: 'number',
        },
        trim_start_ms: {
            type: 'number',
        },
        trim_end_ms: {
            type: 'number',
        },
        created_at: {
            type: 'string',
            isRequired: true,
            format: 'date-time',
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
            type: 'string',
            isRequired: true,
        },
        duration: {
            type: 'number',
            isRequired: true,
        },
        seed: {
            type: 'any-of',
            contains: [{
                type: 'number',
            }, {
                type: 'null',
            }],
            isRequired: true,
        },
        instruct: {
            type: 'any-of',
            contains: [{
                type: 'string',
            }, {
                type: 'null',
            }],
            isRequired: true,
        },
        generation_created_at: {
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
