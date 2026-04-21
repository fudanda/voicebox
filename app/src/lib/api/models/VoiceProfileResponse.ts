/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EffectConfig } from './EffectConfig';
/**
 * Response model for voice profile.
 */
export type VoiceProfileResponse = {
    id: string;
    name: string;
    description: (string | null);
    language: string;
    avatar_path?: (string | null);
    effects_chain?: (Array<EffectConfig> | null);
    voice_type?: string;
    preset_engine?: (string | null);
    preset_voice_id?: (string | null);
    design_prompt?: (string | null);
    default_engine?: (string | null);
    generation_count?: number;
    sample_count?: number;
    created_at: string;
    updated_at: string;
};

