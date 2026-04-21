/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EffectConfig } from './EffectConfig';
/**
 * Request to apply effects to an existing generation.
 */
export type ApplyEffectsRequest = {
    effects_chain: Array<EffectConfig>;
    /**
     * Version to use as source audio (defaults to clean/original)
     */
    source_version_id?: (string | null);
    /**
     * Label for this version (auto-generated if omitted)
     */
    label?: (string | null);
    /**
     * Set this version as the default
     */
    set_as_default?: boolean;
};

