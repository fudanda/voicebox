/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EffectConfig } from './EffectConfig';
/**
 * Request model for creating an effect preset.
 */
export type EffectPresetCreate = {
    name: string;
    description?: (string | null);
    effects_chain: Array<EffectConfig>;
};

