/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EffectConfig } from './EffectConfig';
/**
 * Request model for updating an effect preset.
 */
export type EffectPresetUpdate = {
    name?: (string | null);
    description?: (string | null);
    effects_chain?: (Array<EffectConfig> | null);
};

