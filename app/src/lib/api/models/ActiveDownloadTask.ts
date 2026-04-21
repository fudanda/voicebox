/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Response model for active download task.
 */
export type ActiveDownloadTask = {
    model_name: string;
    status: string;
    started_at: string;
    error?: (string | null);
    progress?: (number | null);
    current?: (number | null);
    total?: (number | null);
    filename?: (string | null);
};

