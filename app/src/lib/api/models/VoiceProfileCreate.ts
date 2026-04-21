/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request model for creating a voice profile.
 */
export type VoiceProfileCreate = {
    name: string;
    description?: (string | null);
    language?: string;
    voice_type?: (string | null);
    preset_engine?: (string | null);
    preset_voice_id?: (string | null);
    design_prompt?: (string | null);
    default_engine?: (string | null);
};

