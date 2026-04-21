/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GenerationVersionResponse } from './GenerationVersionResponse';
/**
 * Response model for history entry (includes profile name).
 */
export type HistoryResponse = {
    id: string;
    profile_id: string;
    profile_name: string;
    text: string;
    language: string;
    audio_path?: (string | null);
    duration?: (number | null);
    seed?: (number | null);
    instruct?: (string | null);
    engine?: (string | null);
    model_size?: (string | null);
    status?: string;
    error?: (string | null);
    is_favorited?: boolean;
    created_at: string;
    versions?: (Array<GenerationVersionResponse> | null);
    active_version_id?: (string | null);
};

