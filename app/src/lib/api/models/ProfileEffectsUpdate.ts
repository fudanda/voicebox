/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EffectConfig } from './EffectConfig';
/**
 * Request to update the default effects chain on a profile.
 */
export type ProfileEffectsUpdate = {
    /**
     * Effects chain (null to remove)
     */
    effects_chain?: (Array<EffectConfig> | null);
};

