/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $VoiceProfileCreate = {
    description: `Request model for creating a voice profile.`,
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
        language: {
            type: 'string',
            pattern: '^(zh|en|ja|ko|de|fr|ru|pt|es|it|he|ar|da|el|fi|hi|ms|nl|no|pl|sv|sw|tr)$',
        },
        voice_type: {
            type: 'any-of',
            contains: [{
                type: 'string',
                pattern: '^(cloned|preset|designed)$',
            }, {
                type: 'null',
            }],
        },
        preset_engine: {
            type: 'any-of',
            contains: [{
                type: 'string',
                maxLength: 50,
            }, {
                type: 'null',
            }],
        },
        preset_voice_id: {
            type: 'any-of',
            contains: [{
                type: 'string',
                maxLength: 100,
            }, {
                type: 'null',
            }],
        },
        design_prompt: {
            type: 'any-of',
            contains: [{
                type: 'string',
                maxLength: 2000,
            }, {
                type: 'null',
            }],
        },
        default_engine: {
            type: 'any-of',
            contains: [{
                type: 'string',
                maxLength: 50,
            }, {
                type: 'null',
            }],
        },
    },
} as const;
