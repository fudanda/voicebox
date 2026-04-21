/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Health status for a single directory.
 */
export type DirectoryCheck = {
    path: string;
    exists: boolean;
    writable: boolean;
    error?: (string | null);
};

