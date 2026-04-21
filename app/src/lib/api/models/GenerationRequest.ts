/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EffectConfig } from './EffectConfig';
/**
 * Request model for voice generation.
 */
export type GenerationRequest = {
    profile_id: string;
    text: string;
    language?: string;
    seed?: (number | null);
    model_size?: (string | null);
    instruct?: (string | null);
    engine?: (string | null);
    /**
     * Max characters per chunk for long text splitting
     */
    max_chunk_chars?: number;
    /**
     * Crossfade duration in ms between chunks (0 for hard cut)
     */
    crossfade_ms?: number;
    /**
     * Normalize output audio volume
     */
    normalize?: boolean;
    /**
     * Effects chain to apply after generation (overrides profile default)
     */
    effects_chain?: (Array<EffectConfig> | null);
};

