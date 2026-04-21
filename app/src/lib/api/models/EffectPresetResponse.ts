/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EffectConfig } from './EffectConfig';
/**
 * Response model for effect preset.
 */
export type EffectPresetResponse = {
    id: string;
    name: string;
    description?: (string | null);
    effects_chain: Array<EffectConfig>;
    is_builtin?: boolean;
    created_at: string;
};

