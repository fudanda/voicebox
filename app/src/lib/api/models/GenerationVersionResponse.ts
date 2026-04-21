/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EffectConfig } from './EffectConfig';
/**
 * Response model for a generation version.
 */
export type GenerationVersionResponse = {
    id: string;
    generation_id: string;
    label: string;
    audio_path: string;
    effects_chain?: (Array<EffectConfig> | null);
    source_version_id?: (string | null);
    is_default: boolean;
    created_at: string;
};

