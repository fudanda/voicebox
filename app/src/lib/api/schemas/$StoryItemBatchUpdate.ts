/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $StoryItemBatchUpdate = {
    description: `Request model for batch updating story item timecodes.`,
    properties: {
        updates: {
            type: 'array',
            contains: {
                type: 'StoryItemUpdateTime',
            },
            isRequired: true,
        },
    },
} as const;
