/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $GenerationRequest = {
    description: `Request model for voice generation.`,
    properties: {
        profile_id: {
            type: 'string',
            isRequired: true,
        },
        text: {
            type: 'string',
            isRequired: true,
            maxLength: 50000,
            minLength: 1,
        },
        language: {
            type: 'string',
            pattern: '^(zh|en|ja|ko|de|fr|ru|pt|es|it|he|ar|da|el|fi|hi|ms|nl|no|pl|sv|sw|tr)$',
        },
        seed: {
            type: 'any-of',
            contains: [{
                type: 'number',
            }, {
                type: 'null',
            }],
        },
        model_size: {
            type: 'any-of',
            contains: [{
                type: 'string',
                pattern: '^(1\\.7B|0\\.6B|1B|3B)$',
            }, {
                type: 'null',
            }],
        },
        instruct: {
            type: 'any-of',
            contains: [{
                type: 'string',
                maxLength: 500,
            }, {
                type: 'null',
            }],
        },
        engine: {
            type: 'any-of',
            contains: [{
                type: 'string',
                pattern: '^(qwen|qwen_custom_voice|luxtts|chatterbox|chatterbox_turbo|tada|kokoro)$',
            }, {
                type: 'null',
            }],
        },
        max_chunk_chars: {
            type: 'number',
            description: `Max characters per chunk for long text splitting`,
            maximum: 5000,
            minimum: 100,
        },
        crossfade_ms: {
            type: 'number',
            description: `Crossfade duration in ms between chunks (0 for hard cut)`,
            maximum: 500,
        },
        normalize: {
            type: 'boolean',
            description: `Normalize output audio volume`,
        },
        effects_chain: {
            type: 'any-of',
            description: `Effects chain to apply after generation (overrides profile default)`,
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
