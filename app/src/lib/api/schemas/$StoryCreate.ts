/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $StoryCreate = {
    description: `Request model for creating a story.`,
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
    },
} as const;
