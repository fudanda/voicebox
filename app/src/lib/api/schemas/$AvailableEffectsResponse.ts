/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $AvailableEffectsResponse = {
    description: `Response listing all available effect types.`,
    properties: {
        effects: {
            type: 'array',
            contains: {
                type: 'AvailableEffect',
            },
            isRequired: true,
        },
    },
} as const;
