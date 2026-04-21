/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Response model for model status.
 */
export type ModelStatus = {
    model_name: string;
    display_name: string;
    hf_repo_id?: (string | null);
    downloaded: boolean;
    downloading?: boolean;
    size_mb?: (number | null);
    loaded?: boolean;
};

